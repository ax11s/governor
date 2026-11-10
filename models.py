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
import prompts

os.makedirs("logs", exist_ok=True)

# Config
# Every model runs in its own llama.cpp server
llama_dir = r"C:\Users\ozikk\AppData\Local\Microsoft\WinGet\Packages\ggml.llamacpp_Microsoft.Winget.Source_8wekyb3d8bbwe"  # folder with llama-server.exe, leave empty when it is on PATH
brain_model = "unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B-GGUF:UD-Q4_K_XL"  # thinking: each step, typing, questions, and hearing the voice
vl_model = "LiquidAI/LFM3-VL-2B-GGUF:Q4_K_M"     # seeing: pointing at things on the screen
d1_model = "LiquidAI/d1-Omni-2B-GGUF:Q8_0"       # quick decisions

servers = {
    "brain": {"port": 8084, "model": brain_model, "flags": ["--reasoning", "off", "--temp", "0"]},
    # reasoning off: with it the VL model sometimes thinks until the token limit and never answers with the points
    "vl": {"port": 8082, "model": vl_model, "flags": ["--reasoning", "off", "--top-p", "1.0", "--min-p", "0.0", "--no-reasoning-preserve"]},
    "d1": {"port": 8083, "model": d1_model, "flags": ["-b", "8192", "-ub", "8192"]},
}

context = 8192      # tokens per request
audio_rate = 16000  # sample rate of the recorded voice clips
point_tokens = 400     # enough for many points
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


def start_models(names=("brain", "vl", "d1")):
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
# JPEG instead of PNG: about 30 times faster to make and 4 times smaller, the text on it stays readable
def image_to_url(image):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def audio_to_base64(audio):
    samples = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(audio_rate)
        f.writeframes(samples.tobytes())
    return base64.b64encode(buffer.getvalue()).decode()


def chat(name, content, max_tokens=1024):
    body = {"messages": [{"role": "user", "content": content}], "max_tokens": max_tokens}
    reply = post(name, "/v1/chat/completions", body)
    text = reply["choices"][0]["message"]["content"]
    if text is None:
        return ""
    return text.strip()


# Brain - a text reply to a prompt, optionally looking at a screenshot
# max_tokens keeps short answers short, a model keeps writing when it can
def think(prompt, image=None, max_tokens=1024):
    start = time.time()
    content = [{"type": "text", "text": prompt}]
    if image is not None:
        content.append({"type": "image_url", "image_url": {"url": image_to_url(image)}})
    reply = chat("brain", content, max_tokens)
    log(f"brain {time.time() - start:.1f}s: {reply[:200]}")
    return reply


# Brain - writes down what is said in a voice clip
def hear(prompt, audio):
    start = time.time()
    content = [{"type": "text", "text": prompt},
               {"type": "input_audio", "input_audio": {"data": audio_to_base64(audio), "format": "wav"}}]
    reply = chat("brain", content)
    log(f"hear {time.time() - start:.1f}s: {reply[:200]}")
    return reply


# Old version was able to speak, this one only types
def say(text):
    log("say: " + text)


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
               {"type": "text", "text": prompts.fill("point", {"things": lines})}]
    reply = chat("vl", content, max_tokens=point_tokens)
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
            if len(things) != 1:
                continue
            for name in things:  # only one thing was asked for, so the point must be it
                label = name
        x, y = coordinates
        found[label].append((x / 1000, y / 1000))  # the model uses values from 0 to 1000, this is a fraction of the screenshot
    return found


# Decision model - answers to named questions about a text and/or a screenshot in one pass
# before is an optional second screenshot, the screen before the last step
def ask(questions, image=None, state=None, before=None):
    start = time.time()
    images = []
    if image is not None:
        images.append(image_to_url(image))
    if before is not None:
        images.append(image_to_url(before))  # second, so the screen now is always the first picture
    reply = post("d1", "/v1/systemone", {"state": state, "questions": questions, "images": images})
    log(f"d1 {time.time() - start:.2f}s")
    return reply.get("answers", reply)
