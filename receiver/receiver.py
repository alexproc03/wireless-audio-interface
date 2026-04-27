from dataclasses import dataclass
from typing import Optional
import socket
import struct

import sounddevice as sd


FRAME_PAYLOAD_BYTES = 1024


@dataclass
class AudioPacket:
    """
    One parsed UDP audio packet.
    """
    sequence: int
    payload: bytes


@dataclass
class StreamMetrics:
    packets_received: int = 0
    packets_lost: int = 0
    loss_rate: float = 0.0


class MetricsCollector:
    def __init__(self):
        self._received = 0
        self._lost = 0

    def on_real_packet_played(self) -> None:
        self._received += 1

    def on_packet_missing(self) -> None:
        self._lost += 1

    def snapshot(self) -> StreamMetrics:
        total = self._received + self._lost
        return StreamMetrics(
            packets_received=self._received,
            packets_lost=self._lost,
            loss_rate=self._lost / total if total > 0 else 0.0,
        )


class UdpReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = 3333):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None

    def open(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self.host, self.port))
        self._sock.setblocking(False)

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None

    def parse_packet(self, data: bytes) -> AudioPacket:
        if len(data) < 4:
            raise ValueError(f"Datagram too short ({len(data)} bytes)")
        (sequence,) = struct.unpack_from(">I", data, 0)
        return AudioPacket(
            sequence=sequence,
            payload=data[4:],
        )

    def receive_packet(self) -> Optional[AudioPacket]:
        if self._sock is None:
            raise RuntimeError("Socket is not open. Call open() first.")
        try:
            data, _ = self._sock.recvfrom(4096)
        except BlockingIOError:
            return None
        return self.parse_packet(data)


class JitterBuffer:
    """
    Stores packets and releases them in stream order.
    """
    DEPTH = 4  # packets to buffer before playback starts
    SEQ_MOD = 2**32
    SEQ_HALF_RANGE = 2**31

    def __init__(self):
        self.packets: dict[int, AudioPacket] = {}
        self.expected_sequence: Optional[int] = None
        self._ready = False

    def push(self, packet: AudioPacket) -> None:
        """Store packet by stream position."""
        # Lazy init — locks onto whatever sequence the ESP32 starts at
        if self.expected_sequence is None:
            self.expected_sequence = packet.sequence

        # Discard packets that have already passed their slot
        # delta > half-range means packet is behind expected in sequence space
        delta = (packet.sequence - self.expected_sequence) % self.SEQ_MOD
        if delta > self.SEQ_HALF_RANGE:
            return

        self.packets[packet.sequence] = packet

        # Gate playback until DEPTH packets are buffered
        if not self._ready and len(self.packets) >= self.DEPTH:
            self._ready = True

    def pop(self) -> Optional[AudioPacket]:
        """Return the next packet in order, or None if unavailable."""
        # Hold during priming — silence fills in the meantime
        if self.expected_sequence is None or not self._ready:
            return None

        packet = self.packets.pop(self.expected_sequence, None)
        self.expected_sequence = (self.expected_sequence + 1) % self.SEQ_MOD
        return packet


class PlaybackEngine:
    """
    Top-level playback pipeline.

    Owns:
        - UDP receiver
        - jitter buffer
    """
    METRICS_INTERVAL = 100  # print metrics every N steps

    def __init__(
        self,
        receiver: UdpReceiver,
        jitter_buffer: JitterBuffer,
        metrics: MetricsCollector,
    ):
        self.receiver = receiver
        self.jitter_buffer = jitter_buffer
        self.metrics = metrics
        self._step_count = 0

    def write_audio(self, frame: bytes) -> None:
        """Send PCM bytes to the audio device."""
        self._stream.write(frame)

    def step(self) -> None:
        """
        Run one pipeline step.

        Typical behavior:
            - receive zero or more packets
            - push them into the jitter buffer
            - get next packet for playback
            - use silence if missing
            - write final audio frame
        """
        # Drain all available packets into jitter buffer
        while True:
            packet = self.receiver.receive_packet()
            if packet is None:
                break
            self.jitter_buffer.push(packet)

        # Get next in-order packet
        packet = self.jitter_buffer.pop()

        if packet is not None:
            self.metrics.on_real_packet_played()
            frame = packet.payload
        else:
            self.metrics.on_packet_missing()
            frame = b"\x00" * FRAME_PAYLOAD_BYTES

        self.write_audio(frame)

        # Print metrics snapshot periodically
        self._step_count += 1
        if self._step_count % self.METRICS_INTERVAL == 0:
            m = self.metrics.snapshot()
            print(
                f"[metrics] recv={m.packets_received} lost={m.packets_lost} "
                f"loss={m.loss_rate:.1%}"
            )

    def run(self) -> None:
        """
        Main playback loop.
        """
        self.receiver.open()
        try:
            with sd.RawOutputStream(
                samplerate=48000,
                channels=1,
                dtype="int16",
            ) as stream:
                self._stream = stream

                while True:
                    self.step()
        finally:
            self.receiver.close()


def main() -> None:
    receiver = UdpReceiver()
    jitter_buffer = JitterBuffer()
    metrics = MetricsCollector()
    engine = PlaybackEngine(
        receiver=receiver,
        jitter_buffer=jitter_buffer,
        metrics=metrics,
    )
    engine.run()


if __name__ == "__main__":
    main()