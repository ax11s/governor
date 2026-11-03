from flask import Flask, jsonify, render_template

import push_to_talk
from game_status import get_status

app = Flask(__name__)
push_to_talk.start()


@app.route("/")
def index():
    # The page now fills itself in with JavaScript, so we send no data here.
    return render_template("index.html")


# The two /api routes return JSON instead of HTML. The page's JavaScript
# calls them in the background to stay up to date without reloading.

@app.route("/api/status")
def api_status():
    # Slow-ish (checks processes and the game's API), so the page asks every 2 s.
    return jsonify(get_status())


@app.route("/api/talking")
def api_talking():
    # Instant, so the page can ask many times a second.
    return jsonify({"talking": push_to_talk.is_talking()})


if __name__ == "__main__":
    app.run(debug=True)
