# The assistant: listens to the user, decides what to do with the request, and runs the task
import glob
import os
import queue
import threading
import time
import keyboard
import numpy as np
import sounddevice as sd
import prompts
from models import start_models, think, hear, say, ask, log
from screen import settings, open_windows
import runner
from runner import run, parse, plan_text

rate = 16000          # sample rate of the voice recording
max_questions = 2     # clarifying questions per request, so the decision can't loop forever
max_help = 2          # times the assistant asks the user for a tip when it is stuck, before it gives up
skill_chance = 0.75   # how sure the decision model must be that a saved skill fits


# Typed requests: a background thread reads the terminal, so typing and push to talk both work
typed = queue.Queue()


def read_typed():
    while True:
        try:
            line = input().strip()
        except EOFError:  # no terminal to read from
            return
        if line != "":
            typed.put(line)


# What the user said (push to talk: records while right alt is held) or typed in the terminal
def listen():
    print("Hold right alt to speak, or type and press enter...")
    while not keyboard.is_pressed("right alt"):
        if not typed.empty():
            return typed.get()
        time.sleep(0.05)

    # the microphone calls this function with every new piece of sound
    chunks = []

    def save_chunk(indata, frame_count, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(device=settings.get("microphone"), samplerate=rate, channels=1,
                        dtype="float32", callback=save_chunk):
        while keyboard.is_pressed("alt"):
            sd.sleep(50)

    if len(chunks) == 0:
        return ""
    audio = np.concatenate(chunks)[:, 0]
    return hear(prompts.load("transcribe"), audio)


# The main model answers the user, instructions is a prompt file, like "refuse"
def reply_to(instructions, request):
    return think(prompts.fill("reply", {"instructions": prompts.load(instructions), "request": request}))


# Decide what to do with a request: refuse it, ask a question, end the chat or do the task
def handle(request):
    for asked in range(max_questions + 1):
        choices = prompts.choices("decide_choices")
        if asked == max_questions:  # no more questions allowed
            choices.pop("QUESTION_GOAL")
            choices.pop("QUESTION_TIPS")

        question = {"decision": {"type": "choice", "instructions": prompts.load("decide"), "criteria": choices}}
        choice = ask(question, state="The user asks their computer assistant: " + request)["decision"]["choice"]
        log("decision: " + choice)

        match choice:
            case "END":
                say("I can only help with tasks on your computer. Hold alt and tell me what to do, or type it.")
                return
            case "REFUSE":
                say(reply_to("refuse", request))
                return
            case "CONTINUE":
                start_task(request)
                return
            case "QUESTION_GOAL":
                question = reply_to("ask_goal", request)
            case _:  # QUESTION_TIPS
                question = reply_to("ask_tips", request)

        # a question: ask the user and add the answer to the request
        say(question)
        answer = listen()
        request = request + "\nAssistant: " + question + "\nUser: " + answer


# Skills: a skill is skills/<name>.txt, the goal on the first line, then the steps that worked
# {file name: goal} of all saved skills
def load_skills():
    skills = {}
    for path in glob.glob("skills/*.txt"):
        name = os.path.basename(path)[:-4]  # without ".txt"
        with open(path, encoding="utf-8") as f:
            skills[name] = f.readline().strip()
    return skills


# A file name for a new skill, made from its goal
def skill_name(goal):
    name = ""
    for letter in goal.lower():
        if letter.isalnum():
            name += letter
        else:
            name += "_"
    return name[:40].strip("_")


# The saved skill that fits the request, "NEW" when none does
def pick_skill(request):
    skills = load_skills()
    if len(skills) == 0:
        return "NEW"
    choices = dict(skills)
    choices["NEW"] = prompts.load("skill_none")
    question = {"skill": {"type": "choice", "instructions": prompts.load("skill_pick"), "criteria": choices}}
    pick = ask(question, state="The user asks their computer assistant: " + request + "\n" + open_windows())["skill"]["choice"]
    if pick not in skills:
        return "NEW"

    # the choice always picks something, so a second question checks it really fits
    question = {"fits": {"type": "noul", "instructions": prompts.load("skill_fits")}}
    state = "Request: " + request + "\nSaved skill: " + skills[pick] + "\n" + open_windows()
    chance = ask(question, state=state)["fits"]["noul"]
    log(f"skill {pick} fits: {chance:.2f}")
    if chance < skill_chance:
        return "NEW"
    return pick


# Stuck: the main model says what went wrong and asks the user for a tip
# - the tip, or "" when the user says exit (or nothing)
def ask_for_help(request, tried):
    question = think(prompts.fill("ask_help", {"goal": request, "steps": tried}))
    say(question + " Say exit to stop.")
    answer = listen()
    log("tip: " + answer)
    words = answer.lower().replace(".", " ").replace(",", " ").replace("!", " ").split()
    if len(words) == 0 or "exit" in words:
        return ""
    return answer


# Run the task, a saved skill that fits is a hint for the main model,
# when it is stuck it asks the user for a tip, up to max_help times,
# the steps that worked are saved as a skill (they replace the skill that was used, it may have been outdated)
def start_task(request):
    pick = pick_skill(request)
    log("skill: " + pick)
    hint = None
    file = skill_name(request)
    if pick == "NEW":
        say("I haven't done this before, I'll work it out step by step. Press escape to stop me.")
    else:
        with open("skills/" + pick + ".txt", encoding="utf-8") as f:
            f.readline()  # the goal
            hint = parse(f.read())
        log("hint:\n" + plan_text(hint))
        file = pick
        say("On it. Press escape to stop me.")

    tips = ""        # the tips from the user, one per line
    all_steps = []   # the steps that helped, from every try
    for asked in range(max_help + 1):
        # done is always checked against what the user asked, not the skill's goal
        ok, steps, tried = run(request, hint, tips)
        all_steps = all_steps + steps
        if ok or runner.stop or asked == max_help:  # done, escape was pressed, or no more questions
            break
        tip = ask_for_help(request, tried)
        if tip == "":
            say("Okay, I'll stop here.")
            return
        tips = tips + "- " + tip + "\n"
        say("Thanks, I'll try again.")

    if ok and len(all_steps) > 0:
        os.makedirs("skills", exist_ok=True)
        with open("skills/" + file + ".txt", "w", encoding="utf-8") as f:
            f.write(request + "\n" + plan_text(all_steps) + "\n")
    if ok:
        say("Done!")
    else:
        say("Sorry, I couldn't finish the task.")


def main():
    start_models()
    threading.Thread(target=read_typed, daemon=True).start()
    say("Hi! Hold alt and tell me what to do, or type it.")
    while True:
        request = listen()
        log("request: " + request)
        if request != "":
            handle(request)


if __name__ == "__main__":
    main()
