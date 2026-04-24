from dataclasses import dataclass
from typing import Optional
import sounddevice as sd

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


class UdpReceiver:
    """
    Receives UDP datagrams and parses them into AudioPacket objects.
    """

    def parse_packet(self, data: bytes) -> AudioPacket:
        """Parse one UDP datagram into an AudioPacket."""

    def receive_packet(self) -> AudioPacket:
        """Receive and parse one UDP packet."""


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
            frame = packet.payload
        else:
            # use PLC if missing
            plc_frame = self.plc.generate(missing_index=0)
            frame = plc_frame.payload

        # write final audio frame
        self.write_audio(frame)

    def run(self) -> None:
        """
        Main playback loop.
        """

        with sd.RawOutputStream(
            samplerate=48000,
            channels=1,
            dtype="int16",
        ) as stream:
            self._stream = stream

            while True:
                self.step()

def main() -> None:
    receiver = UdpReceiver()
    jitter_buffer = JitterBuffer()
    plc = PacketLossConcealer()
    engine = PlaybackEngine(
        receiver=receiver,
        jitter_buffer=jitter_buffer,
        plc=plc,
    )
    engine.run()


if __name__ == "__main__":
    main()