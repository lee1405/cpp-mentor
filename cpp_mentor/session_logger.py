"""Local session logger: records active study time on the fresher's machine.

Run it in the background while studying:

    python -m cpp_mentor.session_logger start     # begin a session
    python -m cpp_mentor.session_logger stop      # end & save the session
    python -m cpp_mentor.session_logger status    # show current session

It samples the foreground window title every few seconds so the report can
show *what* was being worked on (VS Code, terminal, browser, etc.). This is
not tamper-proof on its own — the real anti-cheat is the verified work — but
it gives you a time signal to cross-check against the work produced.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

SESSION_FILE = DATA_DIR / "active_session.json"
SAMPLE_INTERVAL = 10  # seconds


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _foreground_title() -> str:
    """Best-effort foreground window title (Windows)."""
    if sys.platform != "win32":
        return "unknown"
    try:
        import ctypes

        length = ctypes.windll.user32.GetWindowTextLengthW(ctypes.windll.user32.GetForegroundWindow())
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(ctypes.windll.user32.GetForegroundWindow(), buf, length + 1)
        return buf.value or "unknown"
    except Exception:
        return "unknown"


def start() -> dict:
    if SESSION_FILE.exists():
        print("A session is already running. Use 'stop' first.")
        return json.loads(SESSION_FILE.read_text())
    session = {"started_at": _now(), "samples": []}
    SESSION_FILE.write_text(json.dumps(session, indent=2))
    print(f"Session started at {session['started_at']}. Run 'stop' when done.")
    return session


def stop() -> dict | None:
    if not SESSION_FILE.exists():
        print("No active session found.")
        return None
    session = json.loads(SESSION_FILE.read_text())
    session["ended_at"] = _now()
    session["duration_seconds"] = int(
        (datetime.fromisoformat(session["ended_at"])
         - datetime.fromisoformat(session["started_at"])).total_seconds()
    )
    SESSION_FILE.unlink()

    from .state import add_session, load_state, save_state
    state = load_state()
    add_session(state, session)
    save_state(state)
    print(f"Session saved: {session['duration_seconds']}s of activity logged.")
    return session


def status() -> None:
    if not SESSION_FILE.exists():
        print("No active session.")
        return
    session = json.loads(SESSION_FILE.read_text())
    elapsed = (datetime.fromisoformat(_now())
               - datetime.fromisoformat(session["started_at"])).total_seconds()
    print(f"Active session, started {session['started_at']}, elapsed {int(elapsed)}s.")


def sample_loop() -> None:
    """Continuously sample the foreground window while a session is active."""
    print(f"Sampling every {SAMPLE_INTERVAL}s. Ctrl+C to stop.")
    try:
        while True:
            if SESSION_FILE.exists():
                session = json.loads(SESSION_FILE.read_text())
                session["samples"].append({"at": _now(), "window": _foreground_title()})
                SESSION_FILE.write_text(json.dumps(session, indent=2))
            time.sleep(SAMPLE_INTERVAL)
    except KeyboardInterrupt:
        print("\nSampling stopped.")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()
    elif cmd == "sample":
        sample_loop()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
