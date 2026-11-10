# Runs a task step by step: the main model picks each step, the hands do it, the checker rates it
import sys
import time
import keyboard
from PIL import ImageDraw
import prompts
from models import start_models, think, ask, point, log
from screen import screenshot, screen_changed, open_windows, active_title, window_place
from hands import pause, go_address, do_step

max_steps = 30        # steps of a task before giving up
max_no_progress = 6   # steps in a row that did not get closer to the goal before giving up
max_loops = 300       # rounds of a game loop before giving up
step_tokens = 120     # length of a step reply, a Thought line and one step need much less than this
step_delay = 0.5      # seconds for the screen to settle after a step (GO and SEARCH wait for the page themselves)
actions = ["DOUBLE CLICK", "CLICK ALL", "CLICK", "TYPE", "WRITE", "KEY", "WAIT", "LOOP", "SWITCH", "GO", "SEARCH"]
common_words = ["open", "start", "launch", "play", "show", "find", "please", "search", "want", "that", "this",
                "with", "from", "into", "what", "about", "there", "which", "make", "give", "some", "then",
                "would", "like", "could", "should", "channel", "video", "videos", "page", "website", "site", "app",
                "the", "and", "for", "his", "her", "its", "our", "their", "any", "all", "one", "out"]  # words of a goal that are not names


# Escape stops the task
stop = False


def press_escape(event):
    global stop
    stop = True


keyboard.on_press_key("esc", press_escape)


# Steps as text
def parse(text):
    steps = []
    for line in text.splitlines():
        line = line.lstrip(" \t0123456789.)*-").strip()  # removes the numbering, like "1."
        for action in actions:
            if line.upper().startswith(action):
                what = line[len(action):].strip(" :")
                steps.append((action, what))
                break
    return steps


def plan_text(steps):
    lines = []
    for n in range(len(steps)):
        action, what = steps[n]
        lines.append(f"{n + 1}. {action} {what}".strip())
    return "\n".join(lines)


# Prevent multiple steps from one line
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


# What the goal is about, asked once per task
def normalize(text):
    result = ""
    for letter in text.lower():
        if letter.isalnum():
            result += letter
    return result


# Main model - the app, game or website the goal ends in, like "YouTube" for "search for MrBeast on youtube"
# "" when it names none (like "show me a funny video"), the name must be in the goal so the model can't make one up
def goal_name(goal):
    reply = think(prompts.fill("goal_name", {"goal": goal}), max_tokens=20).strip(" .\"'")
    for ending in [".com", ".org", ".net", ".tv"]:
        if reply.lower().endswith(ending):
            reply = reply[:-len(ending)]
    if reply.upper().startswith("NONE") or normalize(reply) == "" or normalize(reply) not in normalize(goal):
        log(f"the goal names no app or website ({reply})")
        return ""
    log("the goal names: " + reply)
    return reply


# Main model - what the goal wants to find inside the app or website, like "mrbeast" for "search youtube for mrbeast"
# "" when it is nothing specific, the words must be in the goal so the model can't make them up
def goal_thing(goal, name):
    if name == "":  # without an app or website it is vague, like "a funny video", a video title won't say "funny"
        return ""
    reply = think(prompts.fill("goal_thing", {"goal": goal}), max_tokens=20).strip(" .\"'")
    words = []
    if not reply.upper().startswith("NONE"):
        for word in reply.split():
            word = normalize(word.replace("'s", "").replace("’s", ""))  # "beast's" is "beast", not "beasts"
            if len(word) >= 3 and word not in common_words and word in normalize(goal) and word not in normalize(name):
                words.append(word)
    thing = " ".join(words)
    if thing == "":
        log(f"the goal wants nothing specific inside it ({reply})")
    else:
        log("the goal wants to find: " + thing)
    return thing


# Is it done?
# Both models say "done" too easily
def title_missing(name, thing):
    if name != "" and normalize(name) not in normalize(window_place()):
        return f"the window in front \"{active_title()}\" is not {name}"
    if thing != "":
        title = normalize(active_title())
        for word in thing.split():
            if word in title:
                return ""
            if word.endswith("s") and word[:-1] in title:
                return ""
        return f"the window name \"{active_title()}\" does not show {thing}"
    return ""


# Checker (decision model) - CLOSER, SAME, FURTHER or DONE after a step
# before is the window name before the step, before_image the screenshot before it
def check(goal, steps, step, before, before_image=None):
    now = screenshot()
    moved = "not known"
    if before_image is not None:
        moved = "no"
        if screen_changed(before_image, now):
            moved = "yes"  # like typed text showing up, which does not change the window name
    state = prompts.fill("check_state", {"goal": goal, "steps": steps, "step": step, "before": before,
                                          "after": active_title(), "place": window_place(), "moved": moved})
    question = {"check": {"type": "choice", "instructions": prompts.load("check"), "criteria": prompts.choices("check_choices")}}
    choice = ask(question, now, state, before=before_image)["check"]["choice"]
    log("check: " + choice)
    return choice


# A game loop: the steps repeat until the checker says DONE and the window agrees - succeeded or not
def loop(goal, steps, name, thing):
    for _ in range(max_loops):
        if stop:
            return False
        before = active_title()
        before_image = screenshot()
        for action, what in steps:
            do_step(action, what, goal)  # nothing to click is normal in a game
        pause(step_delay)
        result = check(goal, plan_text(steps), "one round of the loop", before, before_image)
        if result == "DONE" and title_missing(name, thing) == "":
            return True
    log("the loop never reached the goal")
    return False


# Reading the main model's reply (only one step)
def read_step(reply):
    step_line = None
    rest = []
    for line in reply.splitlines():
        line = line.strip()
        if line.lower().startswith("thought"):
            continue
        if step_line is not None:
            rest.append(line)
        elif line.upper().startswith("DONE") or len(parse(line)) > 0:
            step_line = line
    return step_line, rest


# The action written twice, like "CLICK KEY enter" or "CLICK - click the search field", the inner one counts
def fix_step(action, what):
    what = what.lstrip(" -:")
    inner = parse(what)
    if len(inner) > 0 and inner[0][0] != "LOOP":
        if what.startswith(inner[0][0]) or inner[0][0] == action:
            action, what = inner[0]
    return action, clean_step(what)


# Why a step would not work, "" when it is fine - failed is the last step that did not work
def find_problem(action, what, name, failed):
    if what is None or (what == "" and action != "WAIT" and action != "CLICK ALL"):
        return "not a real step, write one action about the screen, without < >"
    if action == "SWITCH" and what.lower() in active_title().lower():
        return "this window is already in front, do the next thing in it"
    if action == "GO" and go_address(what) is None:  # a sentence, like a copied line of the prompt
        return "write only the name or address of the website after GO"
    if action == "GO" and name != "" and normalize(name) not in normalize(what):  # like GO wikipedia.org for YouTube
        return f"this is not the website of the goal, the goal wants {name}"
    if f"{action} {what}" == failed:  # the same step would fail the same way again
        return "you just tried this and it did not work, pick a different step"
    return ""


# Run a task step by step: the main model sees every step done so far and picks the next one,
# the checker rates each step. hint is a saved skill, steps that worked before for a similar goal,
# tips are what the user said when the assistant was stuck before
# - (succeeded, the steps that helped, saved as the skill, the steps tried with their results)
def run(goal, hint=None, tips=""):
    global stop
    stop = False
    name = goal_name(goal)          # the app or website the goal wants, for the done check and GO
    thing = goal_thing(goal, name)  # what the goal wants to find in it, for the done check

    # the GO and SEARCH examples in the prompt are the goal's own website and words, copying them is right
    website = name
    if website == "":
        website = "name"
    words = thing
    if words == "":
        words = "words"
    step_prompt = prompts.fill("step", {"website": website, "thing": words})
    hint_lines = ""
    if hint is not None:
        hint_lines = prompts.fill("hint", {"plan": plan_text(hint)})
    tip_lines = ""
    if tips != "":
        tip_lines = prompts.fill("tips", {"tips": tips})

    done = []          # the steps that helped
    history = []       # the steps with their results, for the main model
    no_progress = 0    # steps in a row that did not get closer
    failed = None      # the last step that did not work, it is not run again right away
    maybe = None       # a step the checker called DONE, saved only when the main model agrees with DONE next

    for _ in range(max_steps):
        if stop:
            return False, done, "\n".join(history)
        if no_progress >= max_no_progress:
            log(f"no progress for {no_progress} steps, giving up")
            return False, done, "\n".join(history)

        # 1. the main model picks the next step
        steps = "\n".join(history)
        if steps == "":
            steps = "none yet"
        state = prompts.fill("step_state", {"active": active_title(), "windows": open_windows(),
                                            "steps": steps, "hint": hint_lines, "tips": tip_lines, "goal": goal})
        before = active_title()
        before_image = screenshot()  # the main model looks at it, and the checker compares it with the screen after the step
        reply = think(step_prompt + "\n\n" + state, before_image, max_tokens=step_tokens)
        number = len(history) + 1
        step_line, rest = read_step(reply)
        if step_line is None:
            history.append(f"{number}. (no step) - reply with a Thought line and one step")
            no_progress += 1
            continue

        # 2. DONE needs the checker and the window name to agree, as a model alone says yes too easily
        if step_line.upper().startswith("DONE"):
            missing = title_missing(name, thing)
            if missing == "":
                if check(goal, steps, "the assistant thinks the goal is reached", active_title()) == "DONE":
                    if maybe is not None:
                        done.append(maybe)  # the step that reached the goal
                    return True, done, "\n".join(history)
                missing = "the goal is not fully reached"
            log("not done: " + missing)
            history.append(f"{number}. DONE - not yet, {missing}, keep going")
            no_progress += 1
            continue

        # 3. a game loop, the lines after LOOP repeat
        action, what = parse(step_line)[0]
        if action == "LOOP":
            loop_steps = parse("\n".join(rest))
            if len(loop_steps) == 0:
                history.append(f"{number}. LOOP - write the steps to repeat on the lines after LOOP")
                no_progress += 1
                continue
            ok = loop(goal, loop_steps, name, thing)
            return ok, done + [("LOOP", "")] + loop_steps, "\n".join(history)

        # 4. steps that would not work are not done, the model is told why
        action, what = fix_step(action, what)
        problem = find_problem(action, what, name, failed)
        text = f"{action} {what}".strip()
        if problem != "":
            log(f"step skipped: {text} ({problem})")
            history.append(f"{number}. {text} - {problem}")
            no_progress += 1
            continue

        # 5. do the step
        log("step " + text)
        maybe = None  # the main model did not agree with the checker's DONE, it does another step
        if not do_step(action, what, goal):
            history.append(f"{number}. {text} - not found on the screen, describe it by the exact text written on it, or try something else")
            failed = text
            no_progress += 1
            continue
        if action != "GO" and action != "SEARCH":  # those two already waited for the page
            pause(step_delay)

        # 6. SWITCH only gets the next step ready, and the code already knows it worked,
        # the checker often calls it FURTHER as the goal is not on the screen yet, so it is not checked
        if action == "SWITCH":
            history.append(f"{number}. {text} - done, that window is in front now")
            done.append((action, what))
            failed = None
            no_progress += 1  # not progress by itself, so switching again and again still ends
            continue

        # 7. the checker rates it
        result = check(goal, steps, text, before, before_image)
        if result == "DONE":
            missing = title_missing(name, thing)
            if missing == "" and name != "":  # the window name agrees, the main model does not have to say DONE as well
                done.append((action, what))
                return True, done, "\n".join(history)
            result = "CLOSER"
            if missing != "":  # the checker was too quick, the goal is not on the screen yet
                log("not done: " + missing)
                history.append(f"{number}. {text} - closer, but not done yet: {missing}")
            else:  # the goal names no app or website, so the window name can't tell, the main model has to agree
                history.append(f"{number}. {text} - the checker thinks the goal may be reached. Look at the screen: "
                               "if it shows exactly what the goal asks for, reply DONE, if not, fix it")
                maybe = (action, what)
                no_progress += 1  # not progress yet, so this can't go on forever
                continue  # it is saved in the skill only when the main model agrees
        else:
            history.append(f"{number}. {text} - {prompts.choices('check_results')[result]}")

        match result:
            case "CLOSER":
                done.append((action, what))  # only steps that helped are saved in the skill
                no_progress = 0
                failed = None
            case "FURTHER":
                no_progress += 2  # a wrong direction counts double, so a task that keeps going the wrong way ends sooner
                failed = text
            case _:  # SAME
                no_progress += 1
                failed = text
    return False, done, "\n".join(history)


# Pointing test - py runner.py "the search box" saves logs/test.png with the points
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
