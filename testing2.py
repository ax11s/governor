import soundfile as sf
import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

model_id = "LiquidAI/LFM3-Omni-2B"
device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.bfloat16 if device == "cuda" else torch.float32

model = AutoModelForMultimodalLM.from_pretrained(
    model_id, dtype=dtype, device_map=device, trust_remote_code=True
).eval()
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

reply, speech = generate([
    {"role": "system", "content": "Respond with interleaved text and audio."},
    {"role": "user", "content": "what is the capital of France?"},
])

print(reply)