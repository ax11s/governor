Philosophy:
1. How can I know what to build?
1.1. Automate repeatable things?
1.2. Show something that brings real results with a fancy demo?
1.3. What Repeatable actions are there in my life?

2. Candidates
2.1. A tool that monitors work and automatically logs things done with a chat bot that can edit logs and update goals - would be useful but complicated, hard to do a demo
2.2. Build a system that automatically play plants vs zombies - simple and looks kinda fun as a demo but is not real comercial use candidate
2.3. Ultra-focus tool that has managed environments where a decision model chooses what apps to open and locks opening other apps until a result is reached
2.4. A calendar app that automatically places new tasks and appointments and learns though docs via the LLM = simple, usable, self learning


Goal:
Build an AI system that sees the users screen and makes decisions based on the prompt provided to it.
Example usage: "Win a game of Plants VS Zombies", "Open youtube", "Open the teams app".

Overview of the structure:
1. Main omnimodal AI - responsible for being the orchestrator between the user and the other models. A user speaks to it, it writes a plan for the task and hands every step of it to the model that is best at it.
2. The Vision model finds where to click on the screen. The Decision model looks at the result of each step and decides what happens next, until the goal is reached or the user says to stop.

In Depth Explaination:
1. Main model gets voice input for the user (hold right alt and speak). Ex. "Win a level of Plants VS Zombies."
2. The Decision model sorts the request: refuse it, end the chat, or go on. The main model asks questions if needed (max 2). Ex. "Any tips on beating this one?"
3. If a saved skill fits the request the Decision model picks it. If not, the main model looks at the screen and plans the task as short lines, one action per line (CLICK, CLICK ALL, TYPE, WRITE, KEY, WAIT, LOOP).
4. The plan is run line by line. CLICK goes to the Vision model, which points at the thing and the mouse clicks it. WRITE goes back to the main model for things like thinking and text input (ex. a search query for a documentary). The lines after LOOP repeat until the goal is reached, ex. for clicking the suns in Plants VS Zombies.
5. After every click the Decision model looks at the screen and chooses: NEXT, WAIT, RETRY, STUCK or DONE.
6. If the plan reached the goal, it is saved as a skill (a text file in skills/, easy to read and edit), so next time it runs without any planning, and the user is informed. If it fails, it goes back to the main model with the reason and the current screen, and a new plan is written (max 3 times).

How to run it:
1. Install llama.cpp (build b11960 or newer) and ``pip install -r requirements.txt``
2. ``py configure.py`` to pick the microphone and the display
3. ``py governor.py`` (the first start downloads the models)
4. Hold escape to stop a running task

Files:
- governor.py - listens to the user, decides what to do with the request, picks or plans the skill
- runner.py - runs a plan: screenshots, mouse and keyboard, the step by step loop, error recovery
- models.py - starts the three models and holds the calls to them (think, say, point, ask)
- configure.py - small CLI to set the microphone and the display
- skills/ 
- logs/ -
- settings.json -

Technology:
1. ``LiquidAI/LFM3-Omni-2B`` model (Q4_K_M) as the thinking LLM with voice and image capabilities
2. ``LiquidAI/LFM3-VL-2B`` model (Q4_K_M) as the vision model that points at things on the screen
3. ``LiquidAI/d1-omni-2B`` model (Q8_0, there is no Q4 build of it) as the decision model
4. llama.cpp as the inference engine, one server for each model

A few words on the technology chosen for this project:
- A small LLM is bad at writing long structured text like JSON, it kept making up names and mixing the formats up. Plain lines that start with one of 7 words are something it can do, so that is what the plan is made of.
- Each model only does what it is good at: the LLM writes, the Vision model points, the Decision model chooses. It is also cheap, so the loop can run a lot of steps.

Other cool stuff:
- The project includes automatic tracking of models speeds and response times in logs (logs/governor.log).
- Works on RAM or VRAM (CPU and GPU inference are both supported).
- Quantized models (Q4_K_M) to keep memory usage low.
- The system includes error looping prevention (max questions, max retries of a step, max new plans, max loops, escape to stop), LLMs and SLMs (especially small ones) loop quite often so these guardrails are a must.
- When a plan runs out of steps the Decision model checks if the goal was really reached, if not a new plan is written.
- The Decision model is warmed up on start, so the first request is not slow.
