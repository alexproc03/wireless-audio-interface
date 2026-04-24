from dataclasses import dataclass
from typing import Optional
import socket
import struct

import sounddevice as sd


@dataclass
class AudioPacket:
    """
    One parsed UDP audio packet.
    """
    sequence: int
    payload: bytes


@dataclass
class PlcFrame:
    """
    One playback-ready frame.
    """
    sequence: int
    payload: bytes
    synthetic: bool


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
    def __init__(self, host: str = "0.0.0.0", port: int = 5005):
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
        if len(data) < 2:
            raise ValueError(f"Datagram too short ({len(data)} bytes)")
        (sequence,) = struct.unpack_from(">H", data, 0)
        return AudioPacket(
            sequence=sequence,
            payload=data[2:],
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

    def __init__(self):
        self.packets: dict[int, AudioPacket] = {}
        self.expected_sequence: Optional[int] = None

    def push(self, packet: AudioPacket) -> None:
        """Store packet by stream position."""

    def pop(self) -> Optional[AudioPacket]:
        """Return the next packet in order, or None if unavailable."""


class PacketLossConcealer:
    """
    Generates substitute audio when a packet is missing.
    """

    def __init__(self):
        self.last_good_packet: Optional[AudioPacket] = None

    def update(self, packet: AudioPacket) -> None:
        """Remember the last good real packet."""

    def generate(self, missing_sequence: int) -> PlcFrame:
        """Generate a synthetic replacement frame."""


class PlaybackEngine:
    """
    Top-level playback pipeline.

    Owns:
        - UDP receiver
        - jitter buffer
        - packet loss concealer
    """

    def __init__(
        self,
        receiver: UdpReceiver,
        jitter_buffer: JitterBuffer,
        plc: PacketLossConcealer,
        metrics: MetricsCollector,
    ):
        self.receiver = receiver
        self.jitter_buffer = jitter_buffer
        self.plc = plc
        self.metrics = metrics

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
            - use PLC if missing
            - write final audio frame
        """
        # receive zero or more packets
        while True:
            packet = self.receiver.receive_packet()
            if packet is None:
                break
            self.jitter_buffer.push(packet)

        # get next packet for playback
        packet = self.jitter_buffer.pop()

        if packet is not None:
            # use real packet
            self.plc.update(packet)
            self.metrics.on_real_packet_played()
            frame = packet.payload
        else:
            # use PLC if missing
            missing_sequence = (
                self.jitter_buffer.expected_sequence
                if self.jitter_buffer.expected_sequence is not None
                else 0
            )
            plc_frame = self.plc.generate(missing_sequence=missing_sequence)
            self.metrics.on_packet_missing()
            frame = plc_frame.payload

        # write final audio frame
        self.write_audio(frame)

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
    plc = PacketLossConcealer()
    metrics = MetricsCollector()
    engine = PlaybackEngine(
        receiver=receiver,
        jitter_buffer=jitter_buffer,
        plc=plc,
        metrics=metrics,
    )
    engine.run()


if __name__ == "__main__":
    main()