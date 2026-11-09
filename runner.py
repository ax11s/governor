import ctypes
import json
import os
import random
import sys
import time
import keyboard
import mss
import numpy as np
import pyautogui
import pygetwindow
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
max_retries = 3         # tries of one step of a saved skill
max_steps = 30          # steps of a new task before giving up
max_no_progress = 6     # steps in a row that did not get closer to the goal before giving up
step_tokens = 120       # length of a step reply, a Thought line and one step need much less than this
max_loops = 300         # rounds of LOOP before giving up
step_delay = 1          # seconds to wait after a step
click_wait = 0.5        # seconds to wait after a click
screenshot_width = 960  # screenshots are shrunk to this, smaller is faster :)
key_delay = (0.05, 0.18)   # seconds between typed letters, random in this range like a person
move_time = (0.3, 0.7)     # seconds a mouse move takes, random in this range
actions = ["CLICK ALL", "CLICK", "TYPE", "WRITE", "KEY", "WAIT", "LOOP", "SWITCH", "GO"]
browsers = ["google chrome", "microsoft edge", "mozilla firefox", "brave", "opera"]  # last part of a browser window name
ignored_windows = ["Program Manager", "Windows Input Experience", "Click to Do"]  # windows of Windows itself
skip_words = ["icon", "desktop", "google", "shortcut"]  # words that are not the name of an app
common_words = ["open", "start", "launch", "play", "show", "find", "please", "search", "want", "that", "this",
                "with", "from", "into", "what", "about", "there", "which", "make", "give", "some", "then",
                "window", "already", "existing", "user", "assistant", "would", "like", "could", "should"]  # words of a goal that are not names
checked = ["CLICK", "CLICK ALL", "WRITE", "GO"]

# Main model
step_prompt = open("promtps/main_step.txt", encoding="utf-8").read()
# the goal is said again at the end, a small model follows what it read last
step_state = ("The window in front: {active}\n{windows}\nSteps done so far:\n{steps}\n\n"
              "Goal: {goal}\nYour reply, a Thought line and one step for this goal:")
write_prompt = "Goal: {goal}\nWrite {what}.\nReply with the text to type only."
name_prompt = ("Request: {goal}\n\nWhich app, game or website does this request want to open or use? "
               "Reply with its name only, or NONE when the request names none.")
thing_prompt = ("Request: {goal}\n\nWhat does this request want to find or see inside the app or website, "
                "like a channel, video, person or topic? Reply with those words only, "
                "or NONE when it is nothing specific or only the app or website itself.")
reached_prompt = ("Goal: {goal}\nThe window in front is: {active}\n\n"
                  "Look at the window in front and the screenshot. Is the goal reached right now? "
                  "Only what the goal asks for counts, nothing more. Answer only YES or NO.")

# Decision model
next_prompt = "What should happen next?"
next_criteria = {
    "NEXT": "The last step worked, but the goal is not reached yet",
    "WAIT": "The screen is still loading or changing",
    "RETRY": "The last step did not work, like a click that missed or did nothing",
    "STUCK": "Something unexpected is in the way, like a popup, an error or a different screen than the plan expects",
    "DONE": "The goal is reached, what the goal asks for is already open on the screen, even if the plan has more steps",
}
next_state = "Goal: {goal}\nPlan:\n{plan}\nThe last step was {step}. The picture shows the screen after it.\n{windows}"

# Checker - after every step of a new task, says how the screen moved compared to the goal
# A step that did something is not progress by itself, only getting to what the goal names is
check_prompt = "Compare the window before and after the last step with the goal. Is the screen now closer to what the goal names?"
check_criteria = {
    "CLOSER": "The screen now shows more of what the goal names (its app, website or thing) than before, like the right text typed into the right field, the address of the right website typed in, or the right page opened",
    "SAME": "Nothing changed, the two pictures look the same, like a click that did nothing. Text that was typed and is now visible is a change, not SAME",
    "FURTHER": "The screen now shows something the goal does not name, like a different website, a search page, an app with a similar name, or a wrong app. A step that worked but went somewhere else is FURTHER",
    "DONE": "The goal is fully reached, the app and website in front are exactly what the goal names, not just a step toward it. "
            "A search page about it, an app with a similar name or a different part of it (like YouTube Music for YouTube) is not DONE",
}
check_state = ("Goal: {goal}\nSteps done so far:\n{steps}\nThe last step was: {step}\n"
               "The window in front before the step: {before}\nThe window in front now: {after}\n"
               "The app and website in front now: {place}\n"
               "The screen changed after the step: {moved}\n"
               "The first picture is the screen now, the second picture is the screen before the step.")
check_results = {  # how the main model sees the checker's answer
    "CLOSER": "closer to the goal",
    "SAME": "nothing changed on the screen",
    "FURTHER": "WRONG DIRECTION, this is not what the goal names. Go back (KEY alt+left in a browser) and try something different",
    "DONE": "the goal looks reached",
}


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


# Names of the open windows, so the models know what is already open
def open_windows():
    lines = []
    for title in pygetwindow.getAllTitles():
        title = title.strip()
        if title == "" or title in ignored_windows or title + "\n" in lines:
            continue
        lines.append(title + "\n")
    if len(lines) == 0:
        return "Open windows: none"
    return "Open windows:\n- " + "- ".join(lines).strip()


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


# Compares two small grayscale copies of the screen
def changed(before, after):
    a = np.asarray(before.convert("L").resize((64, 36)), dtype=np.float32)
    b = np.asarray(after.convert("L").resize((64, 36)), dtype=np.float32)
    return np.abs(a - b).mean() > 2


# Finer than changed(), it also sees small changes like a few typed letters, used by the checker
def screen_changed(before, after):
    a = np.asarray(before.convert("L").resize((480, 270)), dtype=np.int16)
    b = np.asarray(after.convert("L").resize((480, 270)), dtype=np.int16)
    return (np.abs(a - b) > 40).sum() > 30  # pixels that changed a lot, a blinking text cursor is fewer than this


# Fractions of the screenshot to screen pixels
def to_pixels(p):
    x = display["left"] + p[0] * display["width"]
    y = display["top"] + p[1] * display["height"]
    return x, y


# Human-like input, so websites do not take the assistant for a bot
# Wait a bit longer than asked, a random amount
def pause(seconds):
    time.sleep(seconds + random.uniform(0, seconds / 2))


# Move the mouse in a curve through a random point, speeding up and slowing down like a hand
def move(x, y):
    start_x, start_y = pyautogui.position()
    middle_x = (start_x + x) / 2 + random.randint(-60, 60)
    middle_y = (start_y + y) / 2 + random.randint(-60, 60)
    # stay away from the screen corners, pyautogui stops the program there (its fail-safe)
    middle_x = min(max(middle_x, display["left"] + 10), display["left"] + display["width"] - 10)
    middle_y = min(max(middle_y, display["top"] + 10), display["top"] + display["height"] - 10)
    duration = random.uniform(move_time[0], move_time[1])
    pyautogui.moveTo(middle_x, middle_y, duration=duration / 2, tween=pyautogui.easeInQuad)
    pyautogui.moveTo(x + random.randint(-2, 2), y + random.randint(-2, 2), duration=duration / 2, tween=pyautogui.easeOutQuad)


# Type letter by letter with uneven gaps
def type_text(text):
    for letter in text:
        keyboard.write(letter)
        time.sleep(random.uniform(key_delay[0], key_delay[1]))


# Click a point, double-click an icon if the screen did not change (like a selected desktop icon)
# only icons, a double-click in a text field selects one word instead of all the text
def click(p, what=""):
    x, y = to_pixels(p)
    move(x, y)
    pause(0.1)  # a person stops for a moment before clicking
    before = screenshot()
    pyautogui.click()
    time.sleep(click_wait)
    is_icon = "icon" in what.lower() or "desktop" in what.lower() or "shortcut" in what.lower()
    if is_icon and not changed(before, screenshot()):
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


# The small planner opens apps from the desktop even when they are already open,
# so "CLICK the Chrome icon on the desktop" becomes "SWITCH chrome" when a Chrome window is open
def use_open_windows(plan):
    titles = pygetwindow.getAllTitles()
    new_plan = []
    for action, what in plan:
        name = None
        if action == "CLICK" and "desktop" in what.lower():
            for word in what.lower().split():
                word = word.strip(".,'\"")
                if len(word) < 4 or word in skip_words:
                    continue
                for title in titles:
                    if word in title.lower():
                        name = word
                if name is not None:
                    break
        if name is None:
            new_plan.append((action, what))
            continue
        if len(new_plan) > 0 and new_plan[-1][0] == "KEY" and new_plan[-1][1].lower() == "win+d":
            new_plan.pop()  # no need to show the desktop
        new_plan.append(("SWITCH", name))
        log(f"{name} is already open, switching to it instead of \"{what}\"")
    return new_plan


# Running a plan
# Do one step, False when there was nothing to click
def do_step(action, what, goal):
    if action == "CLICK" or action == "CLICK ALL":
        points = point({"target": what}, screenshot())["target"]
        if action == "CLICK":
            points = points[:1]
        for p in points:
            click(p, what)
        return len(points) > 0
    elif action == "TYPE":
        type_text(what)
    elif action == "WRITE":
        text = think(write_prompt.format(goal=goal, what=what), screenshot())
        type_text(text)
    elif action == "KEY":
        keys = what.lower()
        if keys == "win":
            keys = "windows"
        keys = keys.replace("win+", "windows+")
        keyboard.send(keys)
    elif action == "GO":  # a website by its address, in one step, so no search suggestions get clicked
        keyboard.send("ctrl+l")  # selects all the text in the address bar, so the address replaces it
        pause(0.3)
        type_text(go_address(what))
        pause(0.3)
        keyboard.send("enter")
        time.sleep(click_wait * 4)  # the page needs a moment to load
    elif action == "SWITCH":
        return switch(what)
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
    state = next_state.format(goal=goal, plan=plan_text(plan), step=step_text(plan, n), windows=open_windows())
    question = {"next": {"type": "choice", "instructions": next_prompt, "criteria": next_criteria}}
    for _ in range(max_retries):
        choice = ask(question, screenshot(), state)["next"]["choice"]
        log("next: " + choice)
        if choice != "WAIT":
            return choice
        time.sleep(step_delay * 2)
    return "RETRY"


# Main LLM - checks if the goal is reached, the title of the window in front tells a lot,
# like "MrBeast - YouTube - Google Chrome", which is easier for a small model than the screenshot alone
def goal_reached(goal):
    reply = think(reached_prompt.format(goal=goal, active=active_title()), screenshot())
    log("goal reached: " + reply)
    return reply.upper().startswith("YES")


def active_title():
    active = pygetwindow.getActiveWindow()
    if active is None or active.title.strip() == "":
        return "none"
    return active.title


# The app and website of the window in front, from the end of its name, like
# "MrBeast - YouTube - Google Chrome" -> "google chrome youtube"
# "youtube music app - Google Search - Google Chrome" -> "google chrome google search" (a search page, not YouTube)
def window_place():
    parts = active_title().lower().split(" - ")
    place = parts[-1]  # the app, like "visual studio code" or "google chrome"
    if len(parts) > 1 and place in browsers:
        place += " " + parts[-2].split(" | ")[-1]  # in a browser also the website, like "youtube"
    return place


# Letters and digits only, so "Plants vs. Zombies" and "plants vs zombies" or "youtube.com" and "YouTube" compare
def normalize(text):
    return "".join(letter for letter in text.lower() if letter.isalnum())


# Main LLM - the app, game or website the goal wants, like "YouTube" for "search for MrBeast on youtube"
# "" when it names none (like "show me a funny video"), the name must be in the goal so the model can't make one up
def goal_name(goal):
    reply = think(name_prompt.format(goal=goal), max_tokens=20).strip(" .\"'")
    for ending in [".com", ".org", ".net", ".tv"]:
        if reply.lower().endswith(ending):
            reply = reply[:-len(ending)]
    if reply.upper().startswith("NONE") or normalize(reply) == "" or normalize(reply) not in normalize(goal):
        log(f"the goal names no app or website ({reply})")
        return ""
    log("the goal names: " + reply)
    return reply


# Main LLM - what the goal wants to find inside the app or website, like "mrbeast" for "search youtube for mrbeast"
# "" when it is nothing specific, the words must be in the goal so the model can't make them up
def goal_thing(goal, name):
    reply = think(thing_prompt.format(goal=goal), max_tokens=20).strip(" .\"'")
    words = []
    if not reply.upper().startswith("NONE"):
        for word in reply.split():
            word = normalize(word)
            if len(word) >= 3 and word not in common_words and word in normalize(goal) and word not in normalize(name):
                words.append(word)
    thing = " ".join(words)
    if thing == "":
        log(f"the goal wants nothing specific inside it ({reply})")
    else:
        log("the goal wants to find: " + thing)
    return thing


# Both models say "done" too easily, so the app or website in front must be the one the goal names,
# like "Chrome" in "New Tab - Google Chrome" for "Open Chrome", but not for "Go to YouTube"
# and when the goal wants to find something, it must be in the window name too, like "mrbeast - YouTube"
# Each check is skipped when the goal names nothing for it
def title_matches(name, thing=""):
    if name != "":
        place = window_place()
        if normalize(name) not in normalize(place):
            log(f"not done: the app and website in front \"{place}\" are not {name}")
            return False
    if thing != "":
        title = normalize(active_title())
        found = False
        for word in thing.split():
            if word in title:
                found = True
        if not found:
            log(f"not done: \"{active_title()}\" does not show {thing}")
            return False
    return True


# Checker - CLOSER, SAME, FURTHER or DONE after a step
# before is the window title before the step, before_image the screenshot before it
def check(goal, steps, step, before, before_image=None):
    now = screenshot()
    moved = "not known"
    if before_image is not None:
        moved = "no"
        if screen_changed(before_image, now):
            moved = "yes"  # like typed text showing up, which does not change the window title
    state = check_state.format(goal=goal, steps=steps, step=step, before=before, after=active_title(),
                               place=window_place(), moved=moved)
    question = {"check": {"type": "choice", "instructions": check_prompt, "criteria": check_criteria}}
    choice = ask(question, now, state, before=before_image)["check"]["choice"]
    log("check: " + choice)
    return choice


# New tasks, step by step: the main model sees every step done so far and picks the next one,
# the checker rates each step - (succeeded, the steps that worked, saved as the skill)
def explore(goal, name, thing):
    done = []       # (action, what) of the steps that worked
    history = []    # the steps with their results, for the main model
    no_progress = 0
    failed = None   # the last step that did not work, it is not run again right away
    for _ in range(max_steps):
        if stop:
            return False, done
        if no_progress >= max_no_progress:
            log("no progress for " + str(no_progress) + " steps, giving up")
            return False, done

        steps = "\n".join(history)
        if steps == "":
            steps = "none yet"
        state = step_state.format(goal=goal, active=active_title(), windows=open_windows(), steps=steps)
        website = name
        if website == "":
            website = "name"
        prompt = step_prompt.replace("{website}", website)  # the GO example is the goal's own website, copying it is right
        reply = think(prompt + "\n\n" + state, screenshot(), max_tokens=step_tokens)

        # only the first step after the Thought counts, the small model sometimes writes more steps or turns
        step_line = None
        rest = []    # the lines after the step, only used by LOOP
        for line in reply.splitlines():
            line = line.strip()
            if line.lower().startswith("thought"):
                continue
            if step_line is not None:
                rest.append(line)
            elif line.upper().startswith("DONE") or len(parse(line)) > 0:
                step_line = line
        if step_line is None:
            history.append(f"{len(history) + 1}. (no step) - reply with a Thought line and one step")
            no_progress += 1
            continue

        # DONE needs the checker and the window title to agree, as a model alone says yes too easily
        if step_line.upper().startswith("DONE"):
            if check(goal, steps, "the assistant thinks the goal is reached", active_title()) == "DONE" and title_matches(name, thing):
                return True, done
            history.append(f"{len(history) + 1}. DONE - not yet, the goal is not fully reached, keep going")
            no_progress += 1
            continue

        lines = parse(step_line)

        # a game loop: the lines after LOOP repeat until the goal is reached
        if lines[0][0] == "LOOP":
            lines = lines + parse("\n".join(rest))
            if len(lines) == 1:
                history.append(f"{len(history) + 1}. LOOP - write the steps to repeat on the lines after LOOP")
                no_progress += 1
                continue
            ok, reason, n = play(goal, lines, name, thing)
            log("loop: " + reason)
            return ok, done + lines

        action, what = lines[0]
        # the action written twice, like "CLICK KEY enter" or "CLICK - click the search field", the inner one counts
        what = what.lstrip(" -:")
        inner = parse(what)
        if len(inner) > 0 and inner[0][0] != "LOOP" and (what.startswith(inner[0][0]) or inner[0][0] == action):
            action, what = inner[0]
        what = clean_step(what)
        if what is None or (what == "" and action not in ["WAIT", "CLICK ALL"]):
            history.append(f"{len(history) + 1}. {lines[0][0]} {lines[0][1]} - not a real step, write one action about the screen, without < >")
            log("not a real step: " + lines[0][1])
            no_progress += 1
            continue
        text = f"{action} {what}".strip()
        if action == "SWITCH" and what.lower() in active_title().lower():
            history.append(f"{len(history) + 1}. {text} - this window is already in front, do the next thing in it")
            log("already in front: " + what)
            no_progress += 1
            continue
        if action == "GO" and go_address(what) is None:  # a sentence, like a copied line of the prompt
            history.append(f"{len(history) + 1}. GO with a sentence - write only the name or address of the website after GO")
            log("not an address: " + what)
            no_progress += 1
            continue
        if action == "GO" and name != "" and normalize(name) not in normalize(what):  # like GO wikipedia.org for YouTube
            history.append(f"{len(history) + 1}. {text} - this is not the website of the goal, the goal wants {name}")
            log(f"wrong website skipped: {what} (the goal wants {name})")
            no_progress += 1
            continue
        if text == failed:  # the same step would fail the same way again
            history.append(f"{len(history) + 1}. {text} - you just tried this and it did not work, pick a different step")
            log("repeated step skipped: " + text)
            no_progress += 1
            continue

        log("step " + text)
        before = active_title()
        before_image = screenshot()
        if not do_step(action, what, goal):
            history.append(f"{len(history) + 1}. {text} - not found on the screen, try something else")
            failed = text
            no_progress += 1
            continue
        pause(step_delay)

        result = check(goal, steps, text, before, before_image)
        if result == "DONE" and not title_matches(name, thing):  # the checker was too quick, the goal is not on the screen
            result = "CLOSER"
            history.append(f"{len(history) + 1}. {text} - closer, but not done yet: the window does not show {thing or name} yet")
        else:
            history.append(f"{len(history) + 1}. {text} - {check_results.get(result, result)}")
        if result == "CLOSER" or result == "DONE":  # only steps that helped are saved in the skill
            done.append((action, what))
        if result == "DONE":  # the main model does not have to say DONE as well, the window title was checked above
            return True, done
        if result == "CLOSER" or result == "DONE":
            no_progress = 0
            failed = None
        elif result == "FURTHER":
            no_progress += 2  # a wrong direction counts double, so a run that keeps going the wrong way ends sooner
            failed = text
        else:
            no_progress += 1
            failed = text
    return False, done


# The small model sometimes copies the prompt or puts several actions on one line, like
# "CLICK <the thing to click> KEY ctrl+l, TYPE youtube.com" - only the first action is kept,
# None when it is not a real step
def clean_step(what):
    for action in actions:
        cut = what.find(" " + action + " ")  # actions are written in capitals, so "the type box" is not cut
        if cut != -1:
            what = what[:cut]
    # " - " starts a copied result like "... - this is not the website", " and type" a second action
    for joint in [" - ", " and type ", " and press ", " and enter "]:
        cut = what.find(joint)
        if cut != -1:
            what = what[:cut]
    what = what.strip(" ,.;")
    if "<" in what or ">" in what:
        return None
    return what


# GO takes an address or the name of a website, "YouTube" becomes "youtube.com"
# None when it is a sentence and not an address
def go_address(what):
    what = what.strip(" '\"").lower()
    if " " in what or what == "":
        return None
    if "." not in what:
        what += ".com"
    return what


# One attempt at a plan - (succeeded, why it stopped, the step it stopped at)
# name is the app or website the goal wants, from goal_name(), for the same checks as a new task
def play(goal, plan, name="", thing=""):
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
            if loop_start >= len(plan):  # the goal was already checked after the last step
                return False, "the plan finished but the goal is not reached", last
            if not looked:  # check if the game is over
                choice = decide(goal, plan, last)
                if choice == "DONE" and goal_reached(goal) and title_matches(name, thing):
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
        if action == "GO" and name != "" and normalize(name) not in normalize(what):  # a skill saved by mistake
            return False, f"the skill goes to {what}, but the goal wants {name}", n

        found = do_step(action, what, goal)
        if not found:
            if n >= loop_start:  # normal in a game loop
                n += 1
                continue
            retries += 1
            if retries >= max_retries:
                return False, f"\"{what}\" was not found on the screen", n
            pause(step_delay)
            continue

        pause(step_delay)
        if action not in checked and n + 1 < len(plan):  # only some steps are checked
            n += 1
            continue

        looked = True
        choice = decide(goal, plan, n)
        # DONE is picked too easily so it is checked again, and the goal can be reached before the plan ends
        if choice == "DONE" or (choice == "NEXT" and loop_start >= len(plan)):
            if goal_reached(goal) and title_matches(name, thing):
                return True, "done", n
        if choice == "STUCK":
            return False, "something unexpected was on the screen", n
        elif choice == "RETRY":
            retries += 1
            if retries >= max_retries:
                return False, f"the step did not work {retries} times", n
        else:  # NEXT, or a DONE that was not confirmed
            n += 1
            retries = 0


# Play a saved skill, or work out a new task step by step
# (succeeded, the steps, were they worked out step by step so they are worth saving)
# plan is None for a new task, when a saved skill fails the rest is worked out step by step
def run(goal, plan):
    global stop
    stop = False
    name = goal_name(goal)  # the app or website the goal wants, for the done check and GO
    thing = goal_thing(goal, name)  # what the goal wants to find in it, for the done check
    if plan is not None:
        plan = use_open_windows(plan)
        ok, reason, n = play(goal, plan, name, thing)
        log("skill: " + reason)
        if ok and ("LOOP", "") not in plan:  # the goal can be reached early, the steps that did not run are not saved
            plan = plan[:n + 1]
        if ok or reason == "stopped":
            return ok, plan, False
        say("That didn't work, let me work it out step by step.")
    ok, steps = explore(goal, name, thing)
    log(f"step by step: {'done' if ok else 'failed'}\n" + plan_text(steps))
    return ok, steps, True


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
