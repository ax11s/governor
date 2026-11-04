import torch
from transformers import AutoModel

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
main_refusal_prompt ="Provide the reason why the request was refused based on the provided context. Say something like 'I couldn't do it would take too long, sorry!'"


device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float32 if device == "cpu" else torch.bfloat16
model = AutoModel.from_pretrained("LiquidAI/d1-2B", trust_remote_code=True, dtype=dtype).to(device)

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

output = model.system_one("I want to build a website", questions)
a = output["answers"]
urgency = a["question"]["choice"]
print(urgency)