import torch
from transformers import AutoModel

device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float32 if device == "cpu" else torch.bfloat16
model = AutoModel.from_pretrained("LiquidAI/d1-2B", trust_remote_code=True, dtype=dtype).to(device)

questions = {
    "urgency": {"type": "score", "instructions": "How urgent is this ticket?", "criteria": ["low", "medium", "high"]},
}

output = model.system_one("I was charged twice and my parcel never arrived. Please refund one charge.", questions)
a = output["answers"]
urgency = a["urgency"]["legend"][str(int(a["urgency"]["score"]))]
print(urgency)