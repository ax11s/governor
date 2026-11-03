Main idea: 
Build a omni assistant for playing league of legends with the following capabilities:
- Automatically knows which role the user is playing and how to counter each character
- Tells the user about possible ganks when playing a lane role
- Tells user about gank opportunities
- Collects data automatically by automatically pressing F1, F2, F3, F4, F5 and Tab to view players and items
- User can chat via voice with the system to teach it what to do and later on to ask the system for advice
- System automatically tells the user about great items to build in each scenario, also grades enemies and friendlies on risk of winning or losing any given fight

How it works:
- Uses the games API for gathering data at ``https://127.0.0.1:2999/liveclientdata/gamestats``
- Uses the ``LiquidAI/LFM2.5-VL-3B`` model to detect enemy movments and future fights
- Uses the ``LiquidAI/LFM2.5-VL-3B`` model to recomend items based on a auto-improving dataset of champions and their items

Technical details:
- Uses ``LiquidAI/LFM3-Audio-2B`` as the speach to text and text to speach model


A few words on the technical choices in this project:
The models from LiquidAI were chosen due to a need to run on consumer hardware (one of the goals I wanted to reach) and at Q4_K_M quant they fit in 4gb of ram with some room to spare.

LFM2.5-VL-3B Q4_K_M - 2.3gb
LFM3-Audio-2B - 1.5gb