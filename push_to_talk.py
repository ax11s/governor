"""Tracks whether the push-to-talk key is held down, even while League has focus.

pynput listens to the keyboard system-wide in a background thread, so the rest
of the program just calls is_talking() whenever it wants to know.
"""

from pynput import keyboard

TALK_KEY = keyboard.Key.shift_l  # left shift; right shift is keyboard.Key.shift_r

_talking = False  # the leading _ means "private to this file, use is_talking()"


def _on_press(key):
    global _talking  # without this line, Python would create a new local variable
    if key == TALK_KEY:
        _talking = True


def _on_release(key):
    global _talking
    if key == TALK_KEY:
        _talking = False


def start():
    """Start listening in the background. Call once at startup."""
    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True  # don't keep the program alive just for this thread
    listener.start()


def is_talking():
    return _talking


# Test this file on its own: python push_to_talk.py, then hold left shift.
if __name__ == "__main__":
    import time
    start()
    print("Hold left shift... (Ctrl+C to quit)")
    while True:
        print("talking" if is_talking() else "-------", end="\r")
        time.sleep(0.1)
