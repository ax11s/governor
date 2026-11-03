from flask import Flask, render_template
from game_status import get_status

app = Flask(__name__)


@app.route("/")
def index():
    status = get_status()
    # Flask looks for index.html inside the "templates" folder.
    return render_template("index.html", status=status)


if __name__ == "__main__":
    app.run(debug=True)
