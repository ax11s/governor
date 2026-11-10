# The screen: screenshots, the open windows and the window in front
import ctypes
import json
import os
import mss
import numpy as np
import pygetwindow
from PIL import Image

# Screenshot pixels match click pixels even with display scaling
ctypes.windll.shcore.SetProcessDpiAwareness(2)

# Settings from configure.py
settings = {}
if os.path.exists("settings.json"):
    with open("settings.json", encoding="utf-8") as f:
        settings = json.load(f)

# The display to use (from the settings), else the main one
with mss.MSS() as sct:
    monitors = sct.monitors  # number 0 is all displays together
number = settings.get("display", 0)
if 0 < number < len(monitors):
    display = monitors[number]
else:
    display = monitors[1]
    for monitor in monitors[1:]:
        if monitor.get("is_primary"):
            display = monitor

screenshot_width = 960  # screenshots are shrunk to this, smaller is faster :)
ignored_windows = ["Program Manager", "Windows Input Experience", "Click to Do"]  # windows of Windows itself
browsers = ["google chrome", "microsoft edge", "mozilla firefox", "brave", "opera"]  # last part of a browser window name


def screenshot():
    with mss.MSS() as sct:
        shot = sct.grab(display)
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    height = round(image.height * screenshot_width / image.width)
    return image.resize((screenshot_width, height), Image.Resampling.BOX)


# Fractions of the screenshot (0 to 1) to screen pixels
def to_pixels(point):
    x = display["left"] + point[0] * display["width"]
    y = display["top"] + point[1] * display["height"]
    return x, y


# Did the screen change?
def screen_changed(before, after):
    a = np.asarray(before.convert("L").resize((480, 270)), dtype=np.int16)
    b = np.asarray(after.convert("L").resize((480, 270)), dtype=np.int16)
    changed_pixels = (np.abs(a - b) > 40).sum()  # pixels that changed a lot
    return changed_pixels > 30


# Names of the open windows, so the model knosw what is already open
def open_windows():
    titles = []
    for title in pygetwindow.getAllTitles():
        title = title.strip()
        if title != "" and title not in ignored_windows and title not in titles:
            titles.append(title)
    if len(titles) == 0:
        return "Open windows: none"
    text = "Open windows:"
    for title in titles:
        text += "\n- " + title
    return text


# The name of the window in front
def active_title():
    active = pygetwindow.getActiveWindow()
    if active is None or active.title.strip() == "":
        return "none"
    return active.title


def window_place():
    parts = active_title().lower().split(" - ")
    place = parts[-1]  # the app, like "visual studio code" or "google chrome"
    if len(parts) > 1 and place in browsers:
        website = parts[-2].split(" | ")[-1]  # in a browser also the website, like "youtube"
        place = place + " " + website
    return place


# Bring an open window to the front, False when no window has this name
def switch(name):
    for window in pygetwindow.getAllWindows():
        if name.lower() in window.title.lower():
            if window.isMinimized:
                window.restore()
            try:
                window.activate()
            except pygetwindow.PyGetWindowException:
                pass  # Windows sometimes reports an error even when it worked
            return True
    return False
