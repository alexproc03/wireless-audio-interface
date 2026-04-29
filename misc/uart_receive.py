import serial, struct, time, wave

# Script to record audio when over serial
PORT = "COM6"
BAUD = 2_000_000
SAMPLE_RATE = 48000
WAV_FILE = "capture.wav"

ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Port open: {ser.is_open}")
print(f"Baud: {ser.baudrate}")
time.sleep(3)
ser.reset_input_buffer()

all_audio = b''
t_start = time.time()
t_last = t_start

print("Reading... Ctrl+C to stop")
try:
    while True:
        raw = ser.read(8192)
        if raw:
            all_audio += raw
        
        now = time.time()
        if now - t_last >= 1.0:
            samples = len(all_audio) // 2
            elapsed = now - t_start
            rate = samples / elapsed if elapsed > 0 else 0
            if len(all_audio) >= 20:
                snip = struct.unpack('<10h', all_audio[-20:])
            else:
                snip = []
            print(f"bytes: {len(all_audio):8d}  rate: {rate:.0f} samp/s  snip: {list(snip)}")
            t_last = now
except KeyboardInterrupt:
    pass
finally:
    ser.close()
    all_audio = all_audio[:len(all_audio) - (len(all_audio) % 2)]
    
    wav = wave.open(WAV_FILE, "wb")
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(all_audio)
    wav.close()
    
    total = len(all_audio) // 2
    print(f"Saved {WAV_FILE} ({total} samples, {total/SAMPLE_RATE:.1f}s)")