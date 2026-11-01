"""
Generate synthetic WhatsApp voice note audio fixture for hero invoice INV-2026-HERO.
Creates a valid 16-bit PCM Mono 16kHz WAV file simulating a customer voice dispute.
"""
import wave
import math
import struct
from pathlib import Path


def generate_hero_voicenote(dest_path: str = "docs/audio/VOICENOTE-2026-HERO.wav") -> str:
    out_path = Path(dest_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sample_rate = 16000
    duration = 14.5  # seconds
    n_samples = int(sample_rate * duration)

    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        frames = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            # Voice pitch fundamental frequency (140-190 Hz)
            f0 = 165.0 + 25.0 * math.sin(2.0 * math.pi * 1.2 * t)
            # Formant harmonics (speech acoustic profile)
            h1 = 0.50 * math.sin(2.0 * math.pi * f0 * t)
            h2 = 0.30 * math.sin(2.0 * math.pi * 2.0 * f0 * t)
            h3 = 0.15 * math.sin(2.0 * math.pi * 3.0 * f0 * t)
            h4 = 0.05 * math.sin(2.0 * math.pi * 5.0 * f0 * t)
            raw_wave = h1 + h2 + h3 + h4

            # Speech syllabic cadence (3.8 syllables/sec)
            cadence = 0.5 + 0.5 * math.sin(2.0 * math.pi * 3.8 * t)

            # Natural breathing and clause pauses at 3.0s, 7.5s, 11.5s
            if (2.9 <= t <= 3.3) or (7.2 <= t <= 7.8) or (11.2 <= t <= 11.7):
                cadence *= 0.05

            amplitude = int(raw_wave * cadence * 14000.0)
            clamped = max(-32767, min(32767, amplitude))
            frames.extend(struct.pack("<h", clamped))

        wav_file.writeframes(frames)

    return str(out_path)


if __name__ == "__main__":
    p = generate_hero_voicenote()
    print(f"Hero voice note generated successfully at: {p}")

