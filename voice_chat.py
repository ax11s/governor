"""Talk to the coach: your voice -> LFM3-Audio-2B -> your speakers.

One model does all three jobs: speech-to-text, thinking, and text-to-speech.
Before running, start it in another terminal and leave it running:
    llama serve -hf LiquidAI/LFM3-Audio-2B-GGUF:Q4_K_M --port 8081 -ngl 99 -c 8192 -np 1

-ngl 99 puts the whole model on the GPU, -c 8192 caps the conversation length
and -np 1 allows one conversation at a time. The last two keep VRAM use low.

Then run:  python voice_chat.py
"""

import base64
import io
import wave

import numpy as np
import requests
import sounddevice as sd

SERVER = "http://127.0.0.1:8081"
MIC_SAMPLE_RATE = 16000
VOICE = "male"

SYSTEM_PROMPT = (
    "You are Governor, a League of Legends coach talking to the player by voice. "
    "Keep answers short: one to three sentences. "
    "Never use lists, markdown or emojis, because your reply is read aloud. "
    "When the player teaches you something, confirm it in a few words."
)


def record_until_enter():
    """Record from the microphone until the user presses Enter."""
    chunks = []

    def on_audio(data, frames, time, status):
        # sounddevice calls this many times per second with new audio.
        chunks.append(data.copy())

    with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=1, dtype="float32", callback=on_audio):
        input("  Recording... press Enter to stop.")

    if not chunks:
        return None
    # Glue the chunks together into one long 1-D array.
    return np.concatenate(chunks).flatten()


def to_wav_bytes(audio):
    """Pack raw samples into a WAV file in memory (no file on disk)."""
    pcm16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # 2 bytes = 16-bit samples
        wav.setframerate(MIC_SAMPLE_RATE)
        wav.writeframes(pcm16.tobytes())
    return buffer.getvalue()


def speech_to_text(audio):
    """Ask the model to transcribe the recording."""
    audio_b64 = base64.b64encode(to_wav_bytes(audio)).decode()
    return chat([
        # This exact system prompt switches the model into transcription mode.
        {"role": "system", "content": "Perform ASR in English."},
        {"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
        ]},
    ])


# ---------- Thinking ----------

def chat(messages):
    """Send messages to the model and return its text reply."""
    response = requests.post(f"{SERVER}/v1/chat/completions", json={
        "messages": messages,
        "temperature": 0,
    }, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


# ---------- Speaking ----------

def speak(text):
    """Turn text into speech on the server and play it."""
    response = requests.post(f"{SERVER}/tts", json={
        "input": text,
        "voice": VOICE,
        "response_format": "pcm",  # raw float32 samples, easy to play
    }, timeout=120)
    response.raise_for_status()

    # The sample rate is in the header, e.g. "audio/pcm;rate=24000;encoding=float;bits=32"
    content_type = response.headers["Content-Type"]
    rate = int(content_type.split("rate=")[1].split(";")[0])

    samples = np.frombuffer(response.content, dtype=np.float32)
    sd.play(samples, rate)
    sd.wait()  # block until playback finishes


# ---------- Main loop ----------

def main():
    # The conversation so far. The model has no memory of its own, so we resend
    # all of it every turn.
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("Press Enter to talk, or type a message and press Enter. Ctrl+C quits.")
    while True:
        typed = input("\n> ").strip()

        try:
            if typed:
                user_text = typed
            else:
                audio = record_until_enter()
                if audio is None:
                    continue
                user_text = speech_to_text(audio)
                print(f"  You said: {user_text}")
            if not user_text:
                continue

            history.append({"role": "user", "content": user_text})
            reply = chat(history)
            history.append({"role": "assistant", "content": reply})
            print(f"  Governor: {reply}")
            speak(reply)

        except requests.exceptions.ConnectionError:
            print(f"  Can't reach the model. Is `llama serve` running at {SERVER}?")
            # Forget a message that never got an answer.
            if history[-1]["role"] == "user":
                history.pop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye!")
