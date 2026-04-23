from dataclasses import dataclass
from typing import Optional
import socket
import struct


@dataclass
class AudioPacket:
    """
    One parsed UDP audio packet.
    """
    sequence: int
    first_sample_index: int
    timestamp: int
    payload: bytes


@dataclass
class PlcFrame:
    """
    One playback-ready frame.
    """
    payload: bytes
    synthetic: bool
    first_sample_index: int
    timestamp: int


@dataclass
class StreamMetrics:
    packets_received: int = 0
    packets_lost: int = 0
    loss_rate: float = 0.0
 
 
class MetricsCollector:
    def __init__(self):
        self._received = 0
        self._highest_seq: Optional[int] = None
 
    def push(self, packet: AudioPacket) -> None:
        self._received += 1
        if self._highest_seq is None or packet.sequence > self._highest_seq:
            self._highest_seq = packet.sequence
 
    def snapshot(self) -> StreamMetrics:
        if self._highest_seq is None:
            return StreamMetrics()
        expected = self._highest_seq + 1
        lost = max(0, expected - self._received)
        return StreamMetrics(
            packets_received=self._received,
            packets_lost=lost,
            loss_rate=lost / expected if expected > 0 else 0.0,
        )
 
 
class UdpReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = 5005):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
 
    def open(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self.host, self.port))
 
    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None
 
    def parse_packet(self, data: bytes) -> AudioPacket:
    # 2-byte sequence number header — confirm exact format with Alex
        if len(data) < 2:
            raise ValueError(f"Datagram too short ({len(data)} bytes)")
        (sequence,) = struct.unpack_from(">H", data, 0)
        return AudioPacket(
            sequence=sequence,
            first_sample_index=0,  # populate once ESP32 header is finalized
            timestamp=0,           # populate once ESP32 header is finalized
            payload=data[2:],
        )
 
    def receive_packet(self) -> AudioPacket:
        data, _ = self._sock.recvfrom(4096)
        return self.parse_packet(data)


class JitterBuffer:
    """
    Stores packets and releases them in stream order.
    """

    def __init__(self):
        self.packets: dict[int, AudioPacket] = {}
        self.expected_index: int = 0

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

    def generate(self, missing_index: int, timestamp: Optional[int] = None) -> PlcFrame:
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
    ):
        self.receiver = receiver
        self.jitter_buffer = jitter_buffer
        self.plc = plc

    def write_audio(self, frame: bytes) -> None:
        """Send PCM bytes to the audio device."""

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

    def run(self) -> None:
        """
        Main playback loop.
        """