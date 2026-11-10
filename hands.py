# The hands: mouse and keyboard, moved like a person so websites do not take the assistant for a bot,
# and do_step() that does one step of a task
import random
import time
import keyboard
import pyautogui
import prompts
from models import think, point
from screen import display, screenshot, to_pixels, switch, active_title

key_delay = (0.05, 0.18)  # seconds between typed letters, random in this range
move_time = (0.3, 0.7)    # seconds a mouse move takes, random in this range
click_wait = 0.5          # seconds to wait after a click
page_wait = 3             # most seconds to wait for a page to load after GO or SEARCH


# Wait a bit longer than asked, a random amount
def pause(seconds):
    time.sleep(seconds + random.uniform(0, seconds / 2))


# Simulate more natural mouse movement to (try) prevent being picked up by bot blocking systems
def move(x, y):
    start_x, start_y = pyautogui.position()
    middle_x = (start_x + x) / 2 + random.randint(-60, 60)
    middle_y = (start_y + y) / 2 + random.randint(-60, 60)
    # stay away from the screen edges, pyautogui stops the program in a corner (its fail-safe)
    middle_x = min(max(middle_x, display["left"] + 10), display["left"] + display["width"] - 10)
    middle_y = min(max(middle_y, display["top"] + 10), display["top"] + display["height"] - 10)
    duration = random.uniform(move_time[0], move_time[1])
    pyautogui.moveTo(middle_x, middle_y, duration=duration / 2, tween=pyautogui.easeInQuad)
    end_x = x + random.randint(-2, 2)
    end_y = y + random.randint(-2, 2)
    pyautogui.moveTo(end_x, end_y, duration=duration / 2, tween=pyautogui.easeOutQuad)


# Simulate more natural typing
def type_text(text):
    for letter in text:
        keyboard.write(letter)
        time.sleep(random.uniform(key_delay[0], key_delay[1]))


# Simulate more natural clicks (small delay before clicking)
def click(point_on_screen, double=False):
    x, y = to_pixels(point_on_screen)
    move(x, y)
    pause(0.1)
    if double:
        pyautogui.doubleClick()
    else:
        pyautogui.click()
    time.sleep(click_wait)


# Simulate slower reaction time to page load, wait for page
def wait_for_page(old_title):
    end = time.time() + page_wait
    while active_title() == old_title and time.time() < end:
        time.sleep(0.1)
    time.sleep(0.3)  # a moment for the page to draw


# handle web addresses
def go_address(what):
    address = what.strip(" '\"").lower()
    if " " in address or address == "":
        return None
    if "." not in address:
        address = address + ".com"
    return address


# Do one step
def do_step(action, what, goal):
    match action:
        case "CLICK" | "DOUBLE CLICK" | "CLICK ALL":
            points = point({"target": what}, screenshot())["target"]
            if len(points) == 0:
                return False
            if action != "CLICK ALL":
                points = points[:1]  # only the first one
            for p in points:
                click(p, double=(action == "DOUBLE CLICK"))

        case "TYPE":
            type_text(what)

        case "WRITE":  # the main model writes the text like a search query
            text = think(prompts.fill("write", {"goal": goal, "what": what}), screenshot())
            type_text(text)

        case "KEY":
            keys = what.lower()
            if keys == "win":
                keys = "windows"
            keys = keys.replace("win+", "windows+")
            keyboard.send(keys)

        case "GO":  # a website by its address in one step
            old_title = active_title()
            keyboard.send("ctrl+l")  # selects all the text in the address bar so the address replaces it
            pause(0.3)
            type_text(go_address(what))
            pause(0.3)
            keyboard.send("enter")
            wait_for_page(old_title)

        case "SEARCH": 
            points = point({"search box": prompts.load("search_box")}, screenshot())["search box"]
            if len(points) == 0:
                return False
            old_title = active_title()
            click(points[0])
            keyboard.send("ctrl+a")
            pause(0.2)
            type_text(what)
            pause(0.3)
            keyboard.send("enter")
            wait_for_page(old_title)

        case "SWITCH":
            return switch(what)

        case "WAIT":
            try:
                seconds = float(what.split()[0])
            except (ValueError, IndexError): 
                seconds = 1
            time.sleep(seconds)

    return True
