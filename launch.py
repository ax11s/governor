"""Start everything Governor needs with one command:  python launch.py

1. Starts each model server (llama serve) in the background.
2. Waits until every server answers its health check.
3. Starts the Flask web UI.
Ctrl+C stops all of it.
"""

import subprocess
import sys
import time
from pathlib import Path

import requests

LOGS_DIR = Path("logs")

# Each entry is one `llama serve` process. To add a model later (e.g. d1-2B
# for decisions), add another dictionary here with its own port.
MODEL_SERVERS = [
    {
        "name": "audio",
        "model": "LiquidAI/LFM3-Audio-2B-GGUF:Q4_K_M",
        "port": 8081,
        "extra_args": ["-ngl", "99", "-c", "8192", "-np", "1"],
    },
]

STARTUP_TIMEOUT = 600  # seconds; the first start may need to download the model


def start_model_server(server):
    """Start one llama serve process, sending its output to a log file."""
    command = [
        "llama", "serve",
        "-hf", server["model"],
        "--port", str(server["port"]),
        "--no-webui",
        *server["extra_args"],  # the * unpacks the list into separate arguments
    ]
    print(f"Starting {server['name']} model on port {server['port']}")
    return subprocess.Popen(command, stderr=subprocess.STDOUT)


def wait_until_ready(server, process):
    """Poll the server's /health endpoint until it says ok."""
    url = f"http://127.0.0.1:{server['port']}/health"
    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        if process.poll() is not None:
            # poll() returns an exit code once the process has stopped.
            raise RuntimeError(f"{server['name']} server exited. See logs/{server['name']}.log")
        try:
            if requests.get(url, timeout=2).ok:
                print(f"  {server['name']} model ready.")
                return
        except requests.exceptions.RequestException:
            pass  # not listening yet
        time.sleep(1)

    raise RuntimeError(f"{server['name']} server didn't start within {STARTUP_TIMEOUT}s")


def stop_all(processes):
    for process in processes:
        process.terminate()
    for process in processes:
        process.wait()


def main():
    processes = []
    try:
        for server in MODEL_SERVERS:
            process = start_model_server(server)
            processes.append(process)
            wait_until_ready(server, process)

        print("\nStarting web UI at http://127.0.0.1:5000\n")
        flask = subprocess.Popen([sys.executable, "app.py"])
        processes.append(flask)
        flask.wait()

    except KeyboardInterrupt:
        print("\nShutting down...")
    except RuntimeError as error:
        print(f"\nError: {error}")
    finally:
        stop_all(processes)
        print("Stopped.")


if __name__ == "__main__":
    main()
