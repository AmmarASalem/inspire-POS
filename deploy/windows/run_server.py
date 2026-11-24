"""Server entry point for the Windows till, used by the launcher scripts.

Exists because `pythonw.exe` has no console: the launcher used to run the app
via `pythonw -c "import database; ..."`, so any startup failure (bad venv,
missing dependency, locked inspire.db, port already taken) printed a traceback
to a stderr that goes nowhere, and the whole deploy just silently did nothing.

Here the traceback is caught and appended to deploy/windows/server.log instead,
which is the first thing to read when the till comes up blank.

Deliberately does NOT enable Flask's debug mode or reloader -- the reloader
spawns a second process, which is a liability for something meant to run
unattended on a till nobody is watching.
"""
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LOG_PATH = Path(__file__).resolve().parent / "server.log"

HOST = "127.0.0.1"
PORT = 5000


def log(message):
    """Append to server.log. Under pythonw.exe there is no console at all, so
    this file is the only place a message can go."""
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging must never be the thing that stops the till booting


def main():
    # Imports and the DB live next to app.py; don't depend on the caller's cwd.
    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))

    log(f"--- starting Inspire POS ({sys.version.split()[0]}, {sys.executable}) ---")
    try:
        import database
        database.init_db()
        from app import app
        log(f"serving on http://{HOST}:{PORT}/")
        app.run(host=HOST, port=PORT)
    except BaseException:
        # BaseException, not Exception: SystemExit from a failed bind must be
        # logged too, otherwise it is exactly the invisible failure this exists
        # to prevent.
        log("FATAL: server failed to start\n" + traceback.format_exc())
        return 1
    log("server process exited normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
