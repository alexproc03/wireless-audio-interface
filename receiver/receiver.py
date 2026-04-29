from dataclasses import dataclass
from typing import Optional
from collections import deque
import socket
import struct
import threading
import time

import sounddevice as sd
import numpy as np

FRAME_PAYLOAD_BYTES = 128
QUEUE_MAX_FRAMES = 24
QUEUE_TARGET_FRAMES = 7
QUEUE_TRIM_TOLERANCE = 3
GAIN = 2


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
    frames_dropped: int = 0
    frames_silence: int = 0


class MetricsCollector:
    def __init__(self):
        self._received = 0
        self._lost = 0
        self._frames_dropped = 0
        self._frames_silence = 0
        self._lock = threading.Lock()

    def on_real_packet_played(self) -> None:
        with self._lock:
            self._received += 1

    def on_packet_missing(self, count: int = 1) -> None:
        with self._lock:
            self._lost += count

    def on_frame_dropped(self) -> None:
        with self._lock:
            self._frames_dropped += 1

    def on_silence_played(self) -> None:
        with self._lock:
            self._frames_silence += 1

    def snapshot(self) -> StreamMetrics:
        with self._lock:
            total = self._received + self._lost
            return StreamMetrics(
                packets_received=self._received,
                packets_lost=self._lost,
                loss_rate=self._lost / total if total > 0 else 0.0,
                frames_dropped=self._frames_dropped,
                frames_silence=self._frames_silence,
            )


class UdpReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = 3333):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None

    def open(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self.host, self.port))
        self._sock.settimeout(0.05)

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
        except socket.timeout:
            return None
        return self.parse_packet(data)


class FrameQueue:
    """
    Jitter buffer with a single target depth.

    - On push: drops oldest frames if depth has been persistently above target.
    - On pop: returns None until depth reaches target (re-prime), so startup
      and post-underrun recovery use the same code path.
    """

    def __init__(
        self,
        max_frames: int,
        target_frames: int,
        trim_tolerance: int,
        metrics: MetricsCollector,
    ):
        self._frames = deque()
        self._max_frames = max_frames
        self._target_frames = target_frames
        self._trim_threshold = target_frames + trim_tolerance
        self._lock = threading.Lock()
        self._metrics = metrics
        self._primed = False

    def push(self, frame: bytes) -> None:
        if len(frame) != FRAME_PAYLOAD_BYTES:
            return

        with self._lock:
            while len(self._frames) >= self._max_frames:
                self._frames.popleft()
                self._metrics.on_frame_dropped()

            # Drift correction: only trim when depth has clearly exceeded target.
            # Tolerates normal bursts up to (target + tolerance) without dropping.
            if len(self._frames) >= self._trim_threshold:
                self._frames.popleft()
                self._metrics.on_frame_dropped()

            self._frames.append(frame)

    def pop(self) -> Optional[bytes]:
        with self._lock:
            if not self._primed:
                if len(self._frames) >= self._target_frames:
                    self._primed = True
                else:
                    return None
            if not self._frames:
                self._primed = False
                return None
            return self._frames.popleft()

    def size(self) -> int:
        with self._lock:
            return len(self._frames)


class PlaybackEngine:
    """
    Top-level playback pipeline.

    Owns:
        - UDP receiver
        - bounded frame queue
    """
    METRICS_INTERVAL_SEC = 1.0

    def __init__(
        self,
        receiver: UdpReceiver,
        frame_queue: FrameQueue,
        metrics: MetricsCollector,
    ):
        self.receiver = receiver
        self.frame_queue = frame_queue
        self.metrics = metrics

        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._last_sequence: Optional[int] = None
        self._last_metrics_time = 0.0
        self._silence_frame = b"\x00" * FRAME_PAYLOAD_BYTES

    def _rx_loop(self) -> None:
        while self._running:
            packet = self.receiver.receive_packet()
            if packet is None:
                continue

            if self._last_sequence is not None:
                delta = (packet.sequence - self._last_sequence) & 0xFFFFFFFF
                if delta > 1:
                    self.metrics.on_packet_missing(delta - 1)

            self._last_sequence = packet.sequence
            self.frame_queue.push(packet.payload)

    def _audio_callback(self, outdata, frames, time_info, status) -> None:
        if status:
            print(status)

        if frames * 2 != FRAME_PAYLOAD_BYTES:
            outdata[:] = self._silence_frame
            self.metrics.on_silence_played()
            return

        frame = self.frame_queue.pop()
        if frame is None:
            outdata[:] = self._silence_frame
            self.metrics.on_silence_played()
        else:
            samples = np.frombuffer(frame, dtype=np.int16).astype(np.int32)
            samples = np.clip(samples * GAIN, -32768, 32767).astype(np.int16)
            boosted = samples.tobytes()

            outdata[:] = boosted
            self.metrics.on_real_packet_played()

    def run(self) -> None:
        """
        Main playback loop.
        """
        self.receiver.open()
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

        try:
            with sd.RawOutputStream(
                samplerate=48000,
                channels=1,
                dtype="int16",
                blocksize=64,
                device=8,
                latency="low",
                callback=self._audio_callback,
            ) as stream:
                print("stream latency:", stream.latency)

                self._last_metrics_time = time.time()
                while True:
                    now = time.time()
                    if now - self._last_metrics_time >= self.METRICS_INTERVAL_SEC:
                        m = self.metrics.snapshot()
                        print(
                            f"[metrics] recv={m.packets_received} "
                            f"lost={m.packets_lost} "
                            f"loss={m.loss_rate:.1%} "
                            f"dropped={m.frames_dropped} "
                            f"silence={m.frames_silence} "
                            f"queue={self.frame_queue.size()}"
                        )
                        self._last_metrics_time = now
                    time.sleep(0.05)

        finally:
            self._running = False
            self.receiver.close()


def main() -> None:
    receiver = UdpReceiver()
    metrics = MetricsCollector()
    frame_queue = FrameQueue(
        max_frames=QUEUE_MAX_FRAMES,
        target_frames=QUEUE_TARGET_FRAMES,
        trim_tolerance=QUEUE_TRIM_TOLERANCE,
        metrics=metrics,
    )
    engine = PlaybackEngine(
        receiver=receiver,
        frame_queue=frame_queue,
        metrics=metrics,
    )
    engine.run()


if __name__ == "__main__":
    main()