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
Build an AI system that sees the users screen through a video feed and makes decisions based on the prompt provided to it.
Example usage: "Win a game of Plants VS Zombies", "Open youtube", "Open the teams app".

Overview of the structure:
1. Main omnimodal AI - responsible for being the orchestrator between the user and the decision models. A user speaks to it, it writes a prompt for the decision model and starts the decision model loop.
2. The Decision model executes steps until the main AI (or the user) says to end it or the goal is reached.

In Depth Explaination:
1. Main model gets text or voice input for the user. Ex. "Win a level of Plants VS Zombies."
2. The main model asks questions if needed. Ex. "Any tips on beating this one?"
3. The main model plans the prompts, scopes out the environment and makes sure the model has limited choices of where to click, not to confuse it and to improve accuracy.
4. The main model writes a loop and the ending condition so, there is a looped decision model that does the oversight and a decision model that does the actions. The decision model has a option to call on the main model when needed for things like thinking and or text input.
5. If the loop succeeded at reaching the goal, it quits and informs the user. If the loop fails, it goes back to the main model for review and planning again.

Technology:
1. ``LiquidAI/LFM3-Omni-2B`` model as the thinking LLM with voice and video capabilities
2. ``LiquidAI/d1-omni-2B`` model as the decision model
3. llama.cpp as the inference engine

A few words on the technology chosen for this project:

Other cool stuff:
- The project includes autoamtic tracking of models speeds and response times in logs.
- Wortks on Ram or VRAM (CPU and GPU inference are both supported).
- The system includes error looping prevention, LLMs and SLMs (especially small ones) loop quite often so these guardrails are a must.


To do:
- add threading for the user_loop function