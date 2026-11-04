import torch
from transformers import AutoModel

# Capture voice commands (when right ALT key is held, display "listening..." message) from the user and input them to a decision model 

task_context = ""
unloop = 0
value = ""
answer= ""

# Config
# Decision model
base_decision_promopt = "What describes this question best?"
refusal_value = 10
refusal_prompt = "Refuse if the task would take more than " + refusal_value + "hours to complete."
all_clear_prompt = "If the goal seams doable and is clear, choose CLEAR."
not_goal_prompt = 




def user_loop():
    while True:


def decision_ai(decide_goal):
    # decision model setup
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = torch.float32 if device == "cpu" else torch.bfloat16
    model = AutoModel.from_pretrained("LiquidAI/d1-2B", trust_remote_code=True, dtype=dtype).to(device)


    if unloop == 2:
        questions = {
            "question": {"type": "score", "instructions": "What describes this question best?  ", "criteria": ["", "medium", "high"]},
        }
        # decision_ai("decide_goal") - Decide if and what questions should be asked
            # Goal would take too long (Longer than 10 hours) -> main_ai("REFUSE")
            # Goal is clear enough (examples from "promtps\decision_decide_questions.txt") -> main_ai("CONTINUE")    
            # Not a goal -> END
    else:
        # decision_ai("decide_goal") - Decide if and what questions should be asked
            # Goal would take too long (Longer than 10 hours) -> main_ai("REFUSE")
            # If the goal is too ambiguous (examples from promtps\decision_decide_questions.txt) -> main_ai("QUESTION_GOAL") 
            # Goal is clear enough, but tips would be useful (examples from promtps\decision_decide_questions.txt) -> main_ai("QUESTION_TIPS")
            # Goal is clear enough (examples from "promtps\decision_decide_questions.txt") -> main_ai("CONTINUE")    
            # Not a goal -> END
    match value:
        case "REFUSE":
            #say(REFUSE) 


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


