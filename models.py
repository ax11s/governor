import atexit
import base64
import io
import json
import os
import subprocess
import time
import wave
import numpy as np
import requests
import sounddevice as sd

os.makedirs("logs", exist_ok=True)

# Config
# Every model runs in its own llama.cpp server
llama_dir = r"C:\Users\ozikk\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe"  # folder with llama-server.exe and llama-tts.exe, leave empty when they are on PATH
llm_model = "LiquidAI/LFM3-Omni-2B-GGUF:Q4_K_M"  # planning, typing, transcribing and speaking
vl_model = "LiquidAI/LFM3-VL-2B-GGUF:Q4_K_M"     # pointing at things on the screen
d1_model = "LiquidAI/d1-Omni-2B-GGUF:Q8_0"       # quick decisions

servers = {
    "llm": {"port": 8081, "model": llm_model, "flags": ["--reasoning", "off", "--temp", "0"]},
    "vl": {"port": 8082, "model": vl_model, "flags": ["--top-p", "1.0", "--min-p", "0.0", "--no-reasoning-preserve"]},
    "d1": {"port": 8083, "model": d1_model, "flags": ["-b", "8192", "-ub", "8192"]},
}

context = 8192      # tokens per request
audio_rate = 16000  # sample rate of the recorded voice clips
voice = "female"    # or "male"
point_prompt = """Point to each of these things in the picture, every one of them you can see:
{things}
Answer in JSON as a list of points: [{"point_2d": [x, y], "label": "<name>"}, ...] where the label is the name before the colon. Return [] if none are visible."""
warm_up_question = {"warm_up": {"type": "noul", "instructions": "Is this a test?"}}


def log(line):
    line = time.strftime("%H:%M:%S ") + line
    print(line)
    with open("logs/governor.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# Servers
def server_url(name):
    return "http://127.0.0.1:" + str(servers[name]["port"])


def start_server(name):
    server = servers[name]
    command = [os.path.join(llama_dir, "llama-server"), "-hf", server["model"],
               "--port", str(server["port"]), "-c", str(context)] + server["flags"]
    output = open(f"logs/{name}_server.txt", "w", encoding="utf-8")
    process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
    atexit.register(process.kill)  # the server stops when this program stops
    return process


# wait until the server answers, the first start downloads the model
def wait_for_server(name, process):
    while True:
        if process.poll() is not None:
            raise RuntimeError(f"the {name} server stopped, see logs/{name}_server.txt")
        try:
            response = requests.get(server_url(name) + "/health")
            if response.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(1)


def start_models(names=("llm", "vl", "d1")):
    print("Starting the models (the first start downloads them)...")
    processes = {}
    for name in names:
        processes[name] = start_server(name)
    for name in names:
        wait_for_server(name, processes[name])
    if "d1" in names:
        ask(warm_up_question, state="This is a test.")  # the first call is slow, so a warmup is a nice thing to have for measuring long-term performance


def post(name, path, body):
    response = requests.post(server_url(name) + path, json=body)
    if response.status_code != 200:
        raise RuntimeError(f"the {name} server answered {response.status_code}: {response.text}")
    return response.json()


# Converting the pictures and sound to the format servers want
def image_to_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def audio_to_base64(audio):
    samples = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(audio_rate)
        f.writeframes(samples.tobytes())
    return base64.b64encode(buffer.getvalue()).decode()


def chat(name, content):
    body = {"messages": [{"role": "user", "content": content}], "max_tokens": 1024}
    reply = post(name, "/v1/chat/completions", body)
    text = reply["choices"][0]["message"]["content"]
    if text is None:
        return ""
    return text.strip()


# Main LLM - a text reply to a prompt, optionally looking at a screenshot or listening to a voice clip
def think(prompt, image=None, audio=None):
    start = time.time()
    content = [{"type": "text", "text": prompt}]
    if image is not None:
        content.append({"type": "image_url", "image_url": {"url": image_to_url(image)}})
    if audio is not None:
        content.append({"type": "input_audio", "input_audio": {"data": audio_to_base64(audio), "format": "wav"}})
    reply = chat("llm", content)
    log(f"llm {time.time() - start:.1f}s: {reply[:200]}")
    return reply


# Main LLM - say a text out loud
def say(text):
    log("say: " + text)
    command = [os.path.join(llama_dir, "llama-tts"), "-hf", llm_model, "--tts-voice", voice,
               "-p", text, "-o", "logs/say.wav"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        log("speech failed: " + result.stderr[-500:])
        return
    with wave.open("logs/say.wav") as f:
        samples = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
        rate = f.getframerate()
    sd.play(samples, rate)
    sd.wait()


# VL model - where things are on a screenshot
# things is {name: description}, the result is the fraction of the image
def point(things, image):
    found = {}
    for name in things:
        found[name] = []
    if len(things) == 0:
        return found

    start = time.time()
    lines = ""
    for name in things:
        lines += f"- {name}: {things[name]}\n"
    content = [{"type": "image_url", "image_url": {"url": image_to_url(image)}},
               {"type": "text", "text": point_prompt.replace("{things}", lines)}]
    reply = chat("vl", content)
    log(f"vl {time.time() - start:.1f}s: {reply[:200]}")

    items = []
    first = reply.find("[")
    last = reply.rfind("]")
    if first != -1 and last > first:
        try:
            items = json.loads(reply[first:last + 1])
        except ValueError:
            items = []

    for item in items:
        if not isinstance(item, dict):
            continue
        coordinates = item.get("point_2d", [])
        if len(coordinates) != 2:
            continue
        label = item.get("label")
        if label not in found:
            if len(found) == 1:
                label = list(found)[0]  # only one thing was asked for, so the point must be it
            else:
                continue
        found[label].append((coordinates[0] / 1000, coordinates[1] / 1000))  # the model uses values from 0 to 1000
    return found


# Decision model - answers to named questions about a text and/or a screenshot in one pass
def ask(questions, image=None, state=None):
    start = time.time()
    images = []
    if image is not None:
        images.append(image_to_url(image))
    reply = post("d1", "/v1/systemone", {"state": state, "questions": questions, "images": images})
    log(f"d1 {time.time() - start:.2f}s")
    return reply.get("answers", reply)
