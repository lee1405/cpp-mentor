"""Learner state: curriculum progress, exercise attempts, quiz results,
session logs, and daily reports. All persisted as JSON under data/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, REPORTS_DIR, WORK_DIR, ensure_dirs

STATE_FILE = DATA_DIR / "state.json"
CURRICULUM_FILE = DATA_DIR.parent / "curriculum.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "created_at": _now(),
        "current_day": 1,
        "topics": {},          # topic_id -> {"status": "not-started|in-progress|completed", "completed_at": ...}
        "exercises": {},       # exercise_id -> {"status": ..., "attempts": [...], "passed_at": ...}
        "quizzes": {},         # quiz_id -> {"score": x, "total": y, "at": ...}
        "sessions": [],        # list of session records (from session_logger)
        "reports": [],         # list of daily report summaries
    }


def load_state() -> dict[str, Any]:
    ensure_dirs()
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_state()


def save_state(state: dict[str, Any]) -> None:
    ensure_dirs()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_curriculum() -> dict[str, Any]:
    with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_day(curriculum: dict[str, Any], day: int) -> dict[str, Any] | None:
    for d in curriculum.get("days", []):
        if d.get("day") == day:
            return d
    return None


def topic_status(state: dict[str, Any], topic_id: str) -> str:
    return state["topics"].get(topic_id, {}).get("status", "not-started")


def set_topic_status(state: dict[str, Any], topic_id: str, status: str) -> None:
    entry = state["topics"].setdefault(topic_id, {})
    entry["status"] = status
    if status == "completed":
        entry["completed_at"] = _now()
    else:
        entry.pop("completed_at", None)


def record_attempt(state: dict[str, Any], exercise_id: str, attempt: dict[str, Any]) -> None:
    ex = state["exercises"].setdefault(exercise_id, {"status": "not-started", "attempts": []})
    ex["attempts"].append(attempt)
    if attempt.get("passed"):
        ex["status"] = "passed"
        ex["passed_at"] = _now()
    elif attempt.get("passed_with_solution"):
        ex["status"] = "passed_with_solution"
        ex["passed_at"] = _now()
    else:
        ex["status"] = "in-progress"


def record_quiz(state: dict[str, Any], quiz_id: str, score: int, total: int) -> None:
    state["quizzes"][quiz_id] = {"score": score, "total": total, "at": _now()}


def add_session(state: dict[str, Any], session: dict[str, Any]) -> None:
    state["sessions"].append(session)


def add_report(state: dict[str, Any], report: dict[str, Any]) -> None:
    state["reports"].append(report)
    # Also persist a copy as a standalone JSON file for the dashboard.
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"report_{report.get('date', 'unknown')}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def work_path(exercise_id: str, suffix: str) -> Path:
    """Path for a learner's submitted source file for an exercise."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    safe = exercise_id.replace("/", "_").replace("\\", "_")
    return WORK_DIR / f"{safe}_{suffix}"
