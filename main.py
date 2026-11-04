import torch
from transformers import AutoModel, AutoModelForMultimodalLM, AutoProcessor
import sounddevice as sd
import keyboard
import numpy as np

# Initial variable definitions
task_context = ""
unloop = 0
value = ""
answer= ""
listen_allowed = True
task_cron = []
user_input = ""
rate = 16000


# Config
# Decision model
base_decision_promopt = "What describes this question best? Choose the best option out of: "
refusal_value = "10"
refusal_prompt = "REFUSE if the task would take more than " + refusal_value + "hours to complete. "
continue_prompt = "If the goal seams doable and is clear, choose CONTINUE. "
not_goal_prompt = "If the input is not a goal or does not include computer use, choose REFUSE. "
question_goal_prompt = "If the goal is too ambiguous and needs more clarity, choose 'QUESTION_GOAL'"
question_tips_prompt = "If the request is technically complicated like 'Show me an interesting video on youtube' or 'Win a game of X', should choose QUESTION_TIPS. "

# Decision model variables
refusal_acceptance = 0
continue_acceptance = 0
not_goal_acceptance = 0
question_goal_acceptance = 0
question_tips_acceptance = 0
questions = ""

# Main model
refusal_prompt = "Provide the reason why the request was refused based on the provided context. Say something like 'I couldn't do it would take too long, sorry!' Keep is short."
main_goal_question_prompt = "Ask questions about the goal"


# Loading the models
model_id = "LiquidAI/LFM3-Omni-2B"
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.bfloat16 if device == "cuda" else torch.float32

model = AutoModelForMultimodalLM.from_pretrained(
    model_id, dtype=dtype, trust_remote_code=True
).to(device).eval()
processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
codec = processor.audio_tokenizer.to(device=device).eval()

@torch.inference_mode()
def generate(conversation, generation_mode=None, **processor_kwargs):
    inputs = processor.apply_chat_template(
        conversation, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
        processor_kwargs=processor_kwargs,
    ).to(model.device)
    out = model.generate(
        **inputs, max_new_tokens=512, generation_mode=generation_mode,
        audio_temperature=0.4, audio_repetition_penalty=1.2, audio_repetition_window=64,
    )
    prompt_len = inputs["input_ids"].shape[1]
    reply = processor.decode(out.sequences[0, prompt_len : out.sequence_lengths[0]], skip_special_tokens=True)
    speech = None
    if out.audio_lengths[0] > 0:
        speech = codec.decode(out.audio_codes[:1, :, : out.audio_lengths[0]]).audio_values[0].float().cpu()
    return reply, speech

device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float32 if device == "cpu" else torch.bfloat16
model = AutoModel.from_pretrained("LiquidAI/d1-Omni-2B", trust_remote_code=True, dtype=dtype).to(device)


# capture voice commands from the user
def user_loop():
    # TO BE TESTED
    while listen_allowed:
        if keyboard.is_pressed("right alt"):
            decision_ai()


def main_ai(value):

    def say_think(input):
        _, speech = generate([
            {"role": "system", "content": "Perform TTS in American English using a female voice."},
            {"role": "user", "content": input},
        ], generation_mode="audio")
        sd.play(speech.squeeze(0).numpy(), 24_000)
        sd.wait()

    match value:
        case "REFUSE":
            say_think("")
            user_loop()
            context = ""
        case "QUESTION_GOAL":
            answer = say_think()
            context = context + answer
            unloop += 1
            # decision_ai("decide_goal")
        case "QUESTION_TIPS":
            answer = say_think()
            task_context = answer + task_context
            unloop += 1
            # main_ai("CONTINUE")
        case "CONTINUE":
            # main_ai(file.open(main_plan.txt))
            # file.save(plan.txt)


def decision_ai():

    # decision code and modell loop prevention
    if unloop == 2:
        questions = {
            "question": {"type": "choice", "instructions": base_decision_promopt,
            "criteria": {
                "REFUSE": refusal_prompt,
                "CONTINUE": continue_prompt,
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
                "CONTINUE": continue_prompt,
                "END": not_goal_prompt,
            }},
        }       
    
    # Get voice input from user
    clip = np.random.default_rng(0).normal(0, 0.003, 4 * rate).astype(np.float32)
    for start in (0.5, 1.5, 2.5):
        clip[int(start * rate):int(start * rate) + 3200] += 0.3 * np.sin(2 * np.pi * 880 * np.arange(3200) / rate)

    output = model.system_one(None, {
        "beeps": {"type": "number", "instructions": "How many beeps are there?", "range": [0, 10], "step": 1},
        "speech": {"type": "noul", "instructions": "Does someone speak in the recording?"},
    }, media=[{"type": "audio", "audio": clip, "sampling_rate": rate}])
    a = output["answers"]
    decision = a["beeps"]["number"], a["speech"]["noul"] > 0.5

    main_ai(decision)


    main_ai(decision)


