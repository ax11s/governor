import glob
import os
import keyboard
import numpy as np
import sounddevice as sd
from models import start_models, think, say, ask, log
from runner import run, screenshot, write_plan, parse, plan_text, settings

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
skill_prompt = "Which saved skill can complete this request?"
new_skill_prompt = "None of the saved skills fit this request"
request_state = "The user asks their computer assistant: "

# Main model
assistant_context = "You are a voice assistant that does tasks on the user's computer, like opening apps, websites and games or playing them.\n\n"
transcribe_prompt = "Transcribe exactly what the user says. Write the names of apps, games and websites the way they are spelled, like 'Plants vs. Zombies' or 'YouTube'. Reply with the transcription only."
main_end_reply = "I can only help with tasks on your computer. Hold alt and tell me what to do."
main_refusal_prompt = "Provide the reason why the request was refused based on the provided context. Say something like 'I couldn't do it, it would take too long, sorry!' Keep it short."
main_goal_question_prompt = "Ask one short question that makes the user's goal clear."
main_tips_question_prompt = open("promtps/main_ask_tips.txt", encoding="utf-8").read()


# push to talk: records while alt is held, returns what the user said
def listen():
    print("Hold alt to speak...")
    keyboard.wait("right alt")
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
        pick = ask(question, state=request_state + request)["skill"]["choice"]
    log("skill: " + pick)

    if pick == "NEW":
        say("I haven't done this before, let me plan it out.")
        goal = request
        plan = write_plan(goal, screenshot())
        if plan is None:
            say("Sorry, I couldn't come up with a plan for this.")
            return
        pick = skill_name(goal)
    else:
        with open(f"skills/{pick}.txt", encoding="utf-8") as f:
            goal, steps = f.read().split("\n", 1)
        plan = parse(steps)
    log("plan:\n" + plan_text(plan))

    say("On it. Hold escape to stop me.")
    ok, plan = run(goal, plan)
    if ok:
        os.makedirs("skills", exist_ok=True)
        with open(f"skills/{pick}.txt", "w", encoding="utf-8") as f:
            f.write(goal + "\n" + plan_text(plan) + "\n")
    if ok:
        say("Done!")
    else:
        say("Sorry, I couldn't finish the task.")


def main():
    start_models()
    say("Hi! Hold alt and tell me what to do.")
    while True:
        request = listen()
        log("request: " + request)
        if request != "":
            handle(request)


if __name__ == "__main__":
    main()
