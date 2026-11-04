import torch
from transformers import AutoModel, AutoModelForMultimodalLM, AutoProcessor
import soundfile as sf

# Capture voice commands (when right ALT key is held, display "listening..." message) from the user and input them to a decision model 

task_context = ""
unloop = 0
value = ""
answer= ""

# Config
# Decision model
base_decision_promopt = "What describes this question best? Choose the best option out of: "
refusal_value = "10"
refusal_prompt = "REFUSE if the task would take more than " + refusal_value + "hours to complete. "
all_clear_prompt = "If the goal seams doable and is clear, choose CONTINUE. "
not_goal_prompt = "If the input is not a goal or does not include computer use, choose REFUSE. "
question_goal_prompt = "If the goal is too ambiguous and needs more clarity, choose 'QUESTION_GOAL'"
question_tips_prompt = "If the request is technically complicated like 'Show me an interesting video on youtube' or 'Win a game of X', should choose QUESTION_TIPS. "

# Main model
refusal_prompt = "Provide the reason why the request was refused based on the provided context. Say something like 'I couldn't do it would take too long, sorry!'"



def user_loop():
    user_loop()


def main_ai(value):
    match value:
        case "REFUSE":
            # say "The goal you have given me would take more than 10 hours so I cannot do it, sorry!"
            # decision_ai("decide_goal")
        case "QUESTION_GOAL":
            # main_ai(file.open(main_ask_goal.txt))
            # say(questions)
            # answers -> task_context
            unloop += 1
            # decision_ai("decide_goal")
        case "QUESTION_TIPS":
            # main_ai(file.open(main_ask_tips.txt))
            answer = say(questions)
            task_context = answer + task_context
            # main_ai("CONTINUE")
        case "CONTINUE":
            # main_ai(file.open(main_plan.txt))
            # file.save(plan.txt)


def say():



def decision_ai(decide_goal):
    # decision model setup
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float32 if device == "cpu" else torch.bfloat16
    model = AutoModel.from_pretrained("LiquidAI/d1-2B", trust_remote_code=True, dtype=dtype).to(device)


    if unloop == 2:
        questions = {
            "question": {"type": "choice", "instructions": base_decision_promopt,
            "criteria": {
                "REFUSE": refusal_prompt,
                "CONTINUE": all_clear_prompt,
                "END": not_goal_prompt,
            }},
        }
    else:
        questions = {
            "question": {"type": "choice", "instructions": base_decision_promopt,
            "criteria": {
                "REFUSE": refusal_prompt,
                "QUESTION_GOAL": question_goal_prompt,
                "QUESTION_TIPS": question_tips_prompt,
                "CONTINUE": all_clear_prompt,
                "END": not_goal_prompt,
            }},
        }       

    output = model.system_one("I was charged twice and my parcel never arrived. Please refund one charge.", questions)
    a = output["answers"]
    decision = a["urgency"]["legend"][str(int(a["urgency"]["score"]))]

    print(decision)
    # main_ai(decision)


