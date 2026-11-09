import glob
import os
import queue
import threading
import time
import keyboard
import numpy as np
import sounddevice as sd
from models import start_models, think, say, ask, log
from runner import run, parse, plan_text, settings, open_windows

rate = 16000
max_questions = 2  # clarifying questions per request, so the decision can't loop forever


# Config
# Decision model (each prompt describes when its option applies)
base_decision_prompt = "What describes this request best?"
refusal_value = "10"
refusal_prompt = "The goal does not include computer use or would take more than " + refusal_value + " hours to complete"
continue_prompt = "The goal is doable and clear, like opening a named app, game or website"
question_goal_prompt = "The goal is too ambiguous and needs more clarity"
question_tips_prompt = "The request is technically complicated, like 'Show me an interesting video on youtube' or 'Win a game of X'"
end_prompt = "The user is not giving a goal, like talking about their personal life or asking questions"
skill_prompt = "Which saved skill does exactly what this request asks, starting from the windows that are open now?"
new_skill_prompt = "None of the saved skills does exactly this, like when the request names a different app or website, or asks to use a window that is already open"
same_skill_prompt = "Does the saved skill do exactly what the request asks, no more and no less?"
skill_chance = 0.8  # how sure the decision model must be that a saved skill fits
request_state = "The user asks their computer assistant: "

# Main model
assistant_context = "You are a voice assistant that does tasks on the user's computer, like opening apps, websites and games or playing them.\n\n"
# no example names here, the small model copies them into the transcription
transcribe_prompt = "Transcribe exactly what the user says, word for word, and add nothing. Spell the names of apps, games, websites and people correctly. Reply with the transcription only."
main_end_reply ="I can only help with tasks on your computer. Hold alt and tell me what to do, or type it."
main_refusal_prompt = "Provide the reason why the request was refused based on the provided context. Say something like 'I couldn't do it, it would take too long, sorry!' Keep it short."
main_goal_question_prompt = "Ask one short question that makes the user's goal clear."
main_tips_question_prompt = open("promtps/main_ask_tips.txt", encoding="utf-8").read()


# Typed commands: a background thread reads the terminal, so typing and push to talk both work
typed = queue.Queue()


def read_typed():
    while True:
        try:
            line = input().strip()
        except EOFError:  # no terminal to read from
            return
        if line != "":
            typed.put(line)


# returns what the user said (push to talk: records while alt is held) or typed in the terminal
def listen():
    print("Hold right alt to speak, or type and press enter...")
    while not keyboard.is_pressed("right alt"):
        if not typed.empty():
            return typed.get()
        time.sleep(0.05)
    chunks = []

    def callback(indata, frame_count, time_info, status):
        chunks.append(indata.copy())

    with sd.InputStream(device=settings.get("microphone"), samplerate=rate, channels=1,
                        dtype="float32", callback=callback):
        while keyboard.is_pressed("alt"):
            sd.sleep(50)

    if len(chunks) == 0:
        return ""
    audio = np.concatenate(chunks)[:, 0]
    return think(transcribe_prompt, audio=audio)


# decide what to do with a request
def handle(request):
    for asked in range(max_questions + 1):
        criteria = {
            "REFUSE": refusal_prompt,
            "QUESTION_GOAL": question_goal_prompt,
            "QUESTION_TIPS": question_tips_prompt,
            "CONTINUE": continue_prompt,
            "END": end_prompt,
        }
        if asked == max_questions:  # no more questions allowed
            criteria.pop("QUESTION_GOAL")
            criteria.pop("QUESTION_TIPS")

        question = {"decision": {"type": "choice", "instructions": base_decision_prompt, "criteria": criteria}}
        choice = ask(question, state=request_state + request)["decision"]["choice"]
        log("decision: " + choice)

        if choice == "END":
            say(main_end_reply)
            return
        elif choice == "REFUSE":
            say(think(assistant_context + main_refusal_prompt + "\n\nRequest: " + request))
            return
        elif choice == "QUESTION_GOAL":
            question = think(assistant_context + main_goal_question_prompt + "\n\nRequest: " + request)
            say(question)
            request += f"\nAssistant: {question}\nUser: {listen()}"
        elif choice == "QUESTION_TIPS":
            question = think(assistant_context + main_tips_question_prompt + "\n\nRequest: " + request)
            say(question)
            request += f"\nAssistant: {question}\nUser: {listen()}"
        elif choice == "CONTINUE":
            start_task(request)
            return


# Skills: a skill is skills/<name>.txt, the goal on the first line, then the plan lines
def load_skills():
    skills = {}
    for path in glob.glob("skills/*.txt"):
        name = os.path.basename(path)[:-4]
        with open(path, encoding="utf-8") as f:
            skills[name] = f.readline().strip()
    return skills


# a file name for a new skill, made from its goal
def skill_name(goal):
    name = ""
    for letter in goal.lower():
        if letter.isalnum():
            name += letter
        else:
            name += "_"
    return name[:40].strip("_")


# pick a saved skill for the request (or plan a new one) and run it, a plan that worked is saved as a skill.
def start_task(request):
    skills = load_skills()
    pick = "NEW"
    if len(skills) > 0:
        criteria = dict(skills)
        criteria["NEW"] = new_skill_prompt
        question = {"skill": {"type": "choice", "instructions": skill_prompt, "criteria": criteria}}
        pick = ask(question, state=request_state + request + "\n" + open_windows())["skill"]["choice"]
    if pick in skills:  # the choice always picks something, so a second question checks it really fits
        question = {"same": {"type": "noul", "instructions": same_skill_prompt}}
        state = "Request: " + request + "\nSaved skill: " + skills[pick] + "\n" + open_windows()
        chance = ask(question, state=state)["same"]["noul"]
        log(f"skill {pick} fits: {chance:.2f}")
        if chance < skill_chance:
            pick = "NEW"
    log("skill: " + pick)

    goal = request  # success is always checked against what the user asked, not the skill's goal
    plan = None  # a new task is worked out step by step
    if pick == "NEW":
        say("I haven't done this before, I'll work it out step by step. Press escape to stop me.")
    else:
        with open(f"skills/{pick}.txt", encoding="utf-8") as f:
            steps = f.read().split("\n", 1)[1]
        plan = parse(steps)
        log("plan:\n" + plan_text(plan))
        say("On it. Press escape to stop me.")

    ok, plan, worked_out = run(goal, plan)
    # only steps worked out step by step are saved, a saved skill that failed is replaced by the steps that worked
    if ok and worked_out and len(plan) > 0:
        file = skill_name(goal)
        if pick != "NEW":
            file = pick
            log(f"the skill {pick} did not work, it is replaced")
        os.makedirs("skills", exist_ok=True)
        with open(f"skills/{file}.txt", "w", encoding="utf-8") as f:
            f.write(goal + "\n" + plan_text(plan) + "\n")
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
