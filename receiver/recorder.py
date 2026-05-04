import sys
import wave
from pathlib import Path
from typing import Dict

from receiver import UdpReceiver

SAMPLE_RATE = 48000
SAMPLE_BYTES = 2
FRAME_PAYLOAD_BYTES = 128
SAMPLES_PER_PACKET = FRAME_PAYLOAD_BYTES // SAMPLE_BYTES


def write_wav(path: Path, packets: Dict[int, bytes]) -> None:
    if not packets:
        print("No packets received; nothing to save.")
        return

    first = min(packets)
    last = max(packets)
    total_packets = last - first + 1

    buffer = bytearray(total_packets * FRAME_PAYLOAD_BYTES)
    for seq, payload in packets.items():
        offset = (seq - first) * FRAME_PAYLOAD_BYTES
        buffer[offset:offset + FRAME_PAYLOAD_BYTES] = payload

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(SAMPLE_BYTES)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(buffer))

    received = len(packets)
    missing = total_packets - received
    duration = total_packets * SAMPLES_PER_PACKET / SAMPLE_RATE
    print(
        f"Saved {path} ({duration:.1f}s, "
        f"{received}/{total_packets} packets, {missing} silence-filled)"
    )


def main() -> None:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "capture.wav")
    receiver = UdpReceiver()
    receiver.open()
    packets: Dict[int, bytes] = {}

    # The receiver's 50 ms socket timeout keeps the loop responsive to Ctrl+C.
    print(f"Recording to {out_path} (Ctrl+C to stop)...")
    try:
        while True:
            packet = receiver.receive_packet()
            if packet is None:
                continue
            if len(packet.payload) != FRAME_PAYLOAD_BYTES:
                continue
            packets[packet.sequence] = packet.payload
    except KeyboardInterrupt:
        pass
    finally:
        receiver.close()
        write_wav(out_path, packets)


if __name__ == "__main__":
    main()
