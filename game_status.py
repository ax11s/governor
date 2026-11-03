"""Checks whether League of Legends is running and whether a match has started.

This file knows nothing about Flask or web pages. Keeping it separate means we
can reuse these functions later (in the coach loop, in tests, in a script).
"""

import psutil
import requests
import urllib3

# The game serves its data on your own machine, on port 2999.
LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/gamestats"

# The process name of the actual match (not the launcher/lobby client).
GAME_PROCESS_NAME = "League of Legends.exe"

# The game uses a self-signed HTTPS certificate, so we skip verification.
# That's safe here because we only ever talk to 127.0.0.1 (this computer).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def is_game_running():
    """Return True if the League game process is running."""
    for process in psutil.process_iter(["name"]):
        if process.info["name"] == GAME_PROCESS_NAME:
            return True
    return False


def get_game_time():
    """Return the in-game time in seconds, or None if no match is in progress."""
    try:
        response = requests.get(LIVE_CLIENT_URL, verify=False, timeout=1)
    except requests.exceptions.RequestException:
        # Nothing is listening on port 2999: no game, or still loading.
        return None

    if response.status_code != 200:
        return None

    return response.json()["gameTime"]


def get_status():
    """Collect everything the web page needs into one dictionary."""
    game_time = get_game_time()
    return {
        "game_running": is_game_running(),
        "game_started": game_time is not None and game_time > 0,
        "game_time": game_time,
    }


# Lets you test this file on its own: python game_status.py
if __name__ == "__main__":
    print(get_status())
