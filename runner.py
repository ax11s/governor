import ctypes
import json
import os
import sys
import time
import keyboard
import mss
import numpy as np
import pyautogui
from PIL import Image, ImageDraw
from models import start_models, think, say, ask, point, log

# Screenshot pixels match click pixels even with display scaling
ctypes.windll.shcore.SetProcessDpiAwareness(2)

# Settings from configure.py
settings = {}
if os.path.exists("settings.json"):
    with open("settings.json", encoding="utf-8") as f:
        settings = json.load(f)

with mss.MSS() as sct:
    monitors = sct.monitors  # index 0 is all displays together
number = settings.get("display", 0)
if 0 < number < len(monitors):
    display = monitors[number]
else:
    display = monitors[1]
    for monitor in monitors[1:]:
        if monitor.get("is_primary"):
            display = monitor

# Config
max_retries = 3         # tries of one step before a new plan
max_fixes = 10           # new plans per run
max_loops = 300         # rounds of LOOP before giving up
plan_tries = 2          # tries to get a usable plan
step_delay = 1          # seconds to wait after a step
click_wait = 0.5        # seconds to wait after a click
screenshot_width = 960  # screenshots are shrunk to this, smaller is faster :)
actions = ["CLICK ALL", "CLICK", "TYPE", "WRITE", "KEY", "WAIT", "LOOP"]
checked = ["CLICK", "CLICK ALL", "WRITE"]

# Main model
plan_prompt = open("promtps/main_plan.txt", encoding="utf-8").read()
fix_prompt = ("\n\nThe plan below failed at the step \"{step}\" because {reason}.\n{plan}\n"
              "The screenshot shows the screen now. Write a new plan that reaches the goal from this screen.")
retry_plan_prompt = "\n\nWrite only the plan lines, each one starting with one of the actions."
write_prompt = "Goal: {goal}\nWrite {what}.\nReply with the text to type only."

# Decision model
next_prompt = "What should happen next?"
next_criteria = {
    "NEXT": "The last step worked, but the goal is not reached yet",
    "WAIT": "The screen is still loading or changing",
    "RETRY": "The last step did not work, like a click that missed or did nothing",
    "STUCK": "Something unexpected is in the way, like a popup, an error or a different screen than the plan expects",
    "DONE": "The goal is reached, what the goal asks for is already open on the screen, even if the plan has more steps",
}
next_state = "Goal: {goal}\nPlan:\n{plan}\nThe last step was {step}. The picture shows the screen after it."
reached_prompt = "Is the goal reached? Is what the goal asks for, like the named app or website, open on the screen now?"


# Escape stops the run, a press is remembered until the next check so a short click is not missed
stop = False


def press_escape(event):
    global stop
    stop = True


keyboard.on_press_key("esc", press_escape)


# Screen
def screenshot():
    with mss.MSS() as sct:
        shot = sct.grab(display)
    image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    height = round(image.height * screenshot_width / image.width)
    return image.resize((screenshot_width, height))


# Compares two small grayscale copies of the screen
def changed(before, after):
    a = np.asarray(before.convert("L").resize((64, 36)), dtype=np.float32)
    b = np.asarray(after.convert("L").resize((64, 36)), dtype=np.float32)
    return np.abs(a - b).mean() > 2


# Fractions of the screenshot to screen pixels
def to_pixels(p):
    x = display["left"] + p[0] * display["width"]
    y = display["top"] + p[1] * display["height"]
    return x, y


# Click a point, double-click if the screen did not change (like a selected desktop icon)
def click(p):
    x, y = to_pixels(p)
    pyautogui.moveTo(x, y, duration=0.3)
    before = screenshot()
    pyautogui.click()
    time.sleep(click_wait)
    if not changed(before, screenshot()):
        log("the click changed nothing, double-clicking")
        pyautogui.doubleClick()


# Plans
# Text to a list of (action, what) like ("CLICK", "the Play button")
def parse(text):
    plan = []
    for line in text.splitlines():
        line = line.lstrip(" \t0123456789.)*-").strip()  # removes the numbering
        for action in actions:
            if line.upper().startswith(action):
                plan.append((action, line[len(action):].strip(" :")))
                break
    return plan


def step_text(plan, n):
    action, what = plan[n]
    return f"{n + 1}. {action} {what}".rstrip()


def plan_text(plan):
    lines = []
    for n in range(len(plan)):
        lines.append(step_text(plan, n))
    return "\n".join(lines)


# Main LLM - writes a plan, None when it wrote no usable lines
def write_plan(goal, image, problem=""):
    prompt = plan_prompt + "\n\nGoal: " + goal + problem
    for _ in range(plan_tries):
        plan = parse(think(prompt, image))
        if len(plan) > 0:
            return plan
        prompt += retry_plan_prompt
    return None


# Running a plan
# Do one step, False when there was nothing to click
def do_step(action, what, goal):
    if action == "CLICK" or action == "CLICK ALL":
        points = point({"target": what}, screenshot())["target"]
        if action == "CLICK":
            points = points[:1]
        for p in points:
            click(p)
        return len(points) > 0
    elif action == "TYPE":
        keyboard.write(what, delay=0.02)
    elif action == "WRITE":
        text = think(write_prompt.format(goal=goal, what=what), screenshot())
        keyboard.write(text, delay=0.02)
    elif action == "KEY":
        keys = what.lower()
        if keys == "win":
            keys = "windows"
        keys = keys.replace("win+", "windows+")
        keyboard.send(keys)
    elif action == "WAIT":
        words = what.split()
        try:
            seconds = float(words[0])
        except (ValueError, IndexError):
            seconds = 1
        time.sleep(seconds)
    return True


# Decision model - picks what happens next after a step
def decide(goal, plan, n):
    state = next_state.format(goal=goal, plan=plan_text(plan), step=step_text(plan, n))
    question = {"next": {"type": "choice", "instructions": next_prompt, "criteria": next_criteria}}
    for _ in range(max_retries):
        choice = ask(question, screenshot(), state)["next"]["choice"]
        log("next: " + choice)
        if choice != "WAIT":
            return choice
        time.sleep(step_delay * 2)
    return "RETRY"


# Decision model - checks if the goal is reached
def goal_reached(goal):
    question = {"reached": {"type": "noul", "instructions": reached_prompt}}
    chance = ask(question, screenshot(), "Goal: " + goal)["reached"]["noul"]
    log(f"goal reached: {chance:.2f}")
    return chance > 0.5


# One attempt at a plan - (succeeded, why it stopped, the step it stopped at)
def play(goal, plan):
    # the lines after LOOP repeat
    loop_start = len(plan)
    for i in range(len(plan)):
        if plan[i][0] == "LOOP":
            loop_start = i + 1
            break

    n = 0            # current step
    retries = 0      # tries of the step
    rounds = 0       # rounds of the loop
    looked = False   # did the decision model look in this round

    while True:
        if stop:
            return False, "stopped", n

        # End of the plan
        if n >= len(plan):
            last = len(plan) - 1
            if loop_start >= len(plan):
                if goal_reached(goal):
                    return True, "done", last
                return False, "the plan finished but the goal is not reached", last
            if not looked:  # check if the game is over
                choice = decide(goal, plan, last)
                if choice == "DONE":
                    return True, "done", last
                if choice == "STUCK":
                    return False, "something unexpected was on the screen", last
            rounds += 1
            if rounds >= max_loops:
                return False, "the loop never reached the goal", last
            n = loop_start
            looked = False

        action, what = plan[n]
        if action == "LOOP":
            n += 1
            continue
        log("step " + step_text(plan, n))

        found = do_step(action, what, goal)
        if not found:
            if n >= loop_start:  # normal in a game loop
                n += 1
                continue
            retries += 1
            if retries >= max_retries:
                return False, f"\"{what}\" was not found on the screen", n
            time.sleep(step_delay)
            continue

        time.sleep(step_delay)
        if action not in checked and n + 1 < len(plan):  # only some steps are checked
            n += 1
            continue

        looked = True
        choice = decide(goal, plan, n)
        if choice == "DONE":
            return True, "done", n
        elif choice == "STUCK":
            return False, "something unexpected was on the screen", n
        elif choice == "RETRY":
            retries += 1
            if retries >= max_retries:
                return False, f"the step did not work {retries} times", n
        else:  # NEXT
            if n + 1 >= len(plan) and loop_start >= len(plan):  # the last step worked, so the goal is reached
                return True, "done", n
            if loop_start >= len(plan) and goal_reached(goal):  # the goal can be reached before the plan ends
                return True, "done", n
            n += 1
            retries = 0


# Play a plan, write a new one when it fails - (succeeded, the last plan)
def run(goal, plan):
    global stop
    stop = False
    for attempt in range(max_fixes + 1):
        ok, reason, n = play(goal, plan)
        log(f"attempt {attempt + 1}: {reason}")
        if ok or reason == "stopped" or attempt == max_fixes:
            return ok, plan
        say("That didn't work, let me rethink it.")
        problem = fix_prompt.format(step=step_text(plan, n), reason=reason, plan=plan_text(plan))
        new_plan = write_plan(goal, screenshot(), problem)
        if new_plan is not None:
            plan = new_plan
    return False, plan


# Pointing test - python runner.py "the Plants vs. Zombies icon" saves logs/test.png
if __name__ == "__main__":
    start_models(["vl"])
    print("Taking a screenshot in 3 seconds...")
    time.sleep(3)
    image = screenshot()
    points = point({"target": sys.argv[1]}, image)["target"]
    print(points)
    draw = ImageDraw.Draw(image)
    for x, y in points:
        x = x * image.width
        y = y * image.height
        draw.ellipse([x - 8, y - 8, x + 8, y + 8], outline="red", width=3)
    image.save("logs/test.png")
    print("Saved logs/test.png")
