import numpy as np
import torch
from transformers import AutoModel

device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.float32 if device == "cpu" else torch.bfloat16
model = AutoModel.from_pretrained("LiquidAI/d1-Omni-2B", trust_remote_code=True, dtype=dtype).to(device)

# A recording: three short beeps over quiet noise, 16 kHz mono
rate = 16000
clip = np.random.default_rng(0).normal(0, 0.003, 4 * rate).astype(np.float32)
for start in (0.5, 1.5, 2.5):
    clip[int(start * rate):int(start * rate) + 3200] += 0.3 * np.sin(2 * np.pi * 880 * np.arange(3200) / rate)
out = model.system_one(None, {
    "beeps": {"type": "number", "instructions": "How many beeps are there?", "range": [0, 10], "step": 1},
    "speech": {"type": "noul", "instructions": "Does someone speak in the recording?"},  # yes/no: P(yes)
}, media=[{"type": "audio", "audio": clip, "sampling_rate": rate}])
a = out["answers"]
print(a["beeps"]["number"], a["speech"]["noul"] > 0.5)
# 3.0 False
