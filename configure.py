# pick the microphone and the display to use: py configure.py
import json
import os
import mss
import sounddevice as sd

settings = {}
if os.path.exists("settings.json"):
    with open("settings.json", encoding="utf-8") as f:
        settings = json.load(f)


# CLI
def pick(title, options, current):
    print("\n" + title)
    for i in range(len(options)):
        line = f"  {i + 1}. {options[i]}"
        if i == current:
            line += "  <- current"
        print(line)
    answer = input("Number (enter keeps the current one): ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        return int(answer) - 1
    return current


# Microphone
default_driver = sd.query_devices(kind="input")["hostapi"]
mics = []
for device in sd.query_devices():
    if device["max_input_channels"] > 0 and device["hostapi"] == default_driver:
        mics.append(device["name"])

current = None
if settings.get("microphone") in mics:
    current = mics.index(settings["microphone"])

choice = pick("Microphones:", mics, current)
if choice is not None:
    settings["microphone"] = mics[choice]
    print("Testing it, say something for 2 seconds...")
    clip = sd.rec(2 * 16000, samplerate=16000, channels=1, device=mics[choice])
    sd.wait()
    if abs(clip).max() > 0.02:
        print("Heard you!")
    else:
        print("Very quiet, is this the right microphone?")

# Display
with mss.MSS() as sct:
    monitors = sct.monitors[1:]  # the first one is all displays together, so it is skipped
displays = []
primary = 0
for i in range(len(monitors)):
    monitor = monitors[i]
    text = f"{monitor['width']}x{monitor['height']} at ({monitor['left']}, {monitor['top']})"
    if monitor.get("is_primary"):
        text += " primary"
        primary = i
    displays.append(text)

current = settings.get("display", primary + 1) - 1
choice = pick("Displays:", displays, current)
settings["display"] = choice + 1

with open("settings.json", "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=1)
print("\nSaved to settings.json")
