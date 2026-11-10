# Governor
A simple computer control by voice project writte in a 3 days after work :)

## 🎬 "Fancy" demo
[![Watch the video](https://img.youtube.com/vi/0CSZ1eEgQK4/hqdefault.jpg)](https://www.youtube.com/embed/0CSZ1eEgQK4)



## 💭 Thought process for this project (finding what to build)

1. How can I know what to build with AI models locally?
   1. Automate repeatable things?
   2. Show something that brings real results with a "fancy" demo?
   3. What repeatable actions are there in my life?
   4. Opening programs, searching for things
2. Candidates
   1. A tool that monitors work and automatically logs things done with a chat bot that can edit logs and update goals - would be useful but complicated, hard to do a demo
   2. Build a system that automatically play plants vs zombies - simple and looks kinda fun as a demo but is not real comercial use candidate
   3. Ultra-focus tool that has managed environments where a decision model chooses what apps to open and locks opening other apps until a result is reached
   4. A calendar app that automatically places new tasks and appointments and learns though docs via the LLM = simple, usable, self learning
   5. **Navigation, task automation and simple computer use by voice** ⬅️ in the end it landed on this one, simple, yet useful





## 🎯 Goal

Build an AI system that sees the users screen and makes decisions based on the prompt provided to it.

**Example usage:** *"Open youtube"*, *"Open MrBeast's YouTube channel"*, *"Start a game in Plants vs Zombies"*

All of that fitting in consumer grade hardware (**10gb ram limit**), currently around **8gb**, which could be further decreased mainly by using smaller, fine-tunned models.




## 🚀 How to run it

1. Python 3.10 or newer, install llama.cpp (build b11960 or newer) and run:
   ```
   pip install -r requirements.txt
   ```
2. Set `llama_dir` in `models.py` to the folder of `llama-server.exe` (or leave it empty when llama.cpp is on PATH)
3. Pick the microphone and the display:
   ```
   py configure.py
   ```
4. Start it (the first start downloads the models):
   ```
   py governor.py
   ```
5. Press <kbd>Esc</kbd> to stop a running task




## 🧠 Technology

| Role | Model / tool |
|---|---|
| Thinking and vision | `google/Gemma-4-E4B-it-GGUF` |
| Simple decisions | `LiquidAI/d1-omni-2B` (Q4) |
| Inference engine | llama.cpp |

**Models tried before:** `LiquidAI/LFM3-Omni-2B`, `unsloth/NVIDIA-Nemotron-3.5-Bolt-E4B`, `LiquidAI/LFM3-VL-2B`. All of these models turned out to be suboptimal on results and reliability, even though they exceeded on speed.




### A few words on the technology chosen for this project

- A small model is bad at writing long structured text like JSON or a long plan, it kept making up names, copying the examples of its prompt and mixing the formats up. One short step at a time, a line that starts with one of a few words, is something it can do, so that is what the tasks are made of.
- Each model only does what it is good at: the brain thinks and writes, the Vision model points, the Decision model chooses. The Decision model is small and fast, so it can check every step.
- The code checks what the models say where it can, like the window name for `DONE` and the website for `GO`, as small models say "done" too easily and copy the text of their prompt.




## 🤖 When and why AI was used and when and why it was NOT used

In the beginning no AI was used to setup a solid structure of the project for the models to understand. Some code (by Claude AND Qwen) were not written in a format that was concise and fast enough. Some parts did not make sense too - though I did make some mistakes too, like using 3 separate models, with two of the model overlapping. This caused the models to be worse at thinking through stepts, and although it is not perfect in its current state, it is much better with Gemma 4 E4B as the thinking model than with the 2b omni model from LiquidAI.

Later on the speed of development was not good enough for me and the main structure of the project was already done, so I have setteled for using LLMs in the process to finish it faster (and with good results, even though corrections in the system logic were needed).

Even in this ReadMe file (which in about 80% was initially written by Opus 5.5) there were a lot of mistakes, and the process was not documented well - LLMs make mistakes (which are often costly), a lot of people forget that nowadays - from on-job experience, sadly.

The rest was written by hand.

> **In total, around 59% of the code was written by hand and around 41% by Claude and Qwen** (the functions listed below, approximately 342 of 835 lines of code, not counting empty lines and comments). - yes, this was counter by Claude :)

### Functions written by Claude (Opus 5.5 High) and Qwen3.8 Flash Next (locally hosted - Q3_S, MTP, High)

| File | Functions |
|---|---|
| `screen.py` | `screen_changed()`, `open_windows()`, `active_title()`, `window_place()`, `switch()` |
| `hands.py` | `move()` - the improved version, `go_address()`, `wait_for_page()`, `case "WAIT"` in `do_step()` |
| `runner.py` | `parse()`, `press_escape()`, `clean_step()`, `goal_name()`, `goal_thing()`, `title_missing()`, `check()`, `loop()`, `read_step()`, `fix_step()`, `find_problem()`, major part of `run()`, logging |
| `models.py` | `hear()` |
| `governor.py` | `read_typed()`, `reply_to()`, `ask_for_help()` |

Most of the comments were written by Claude (which it did quite well).




## 😅 Fun fact

The bots detection prevention is far from perfect, so I got IP banned from stack overflow lol :D
