"""Daily report: aggregate the day's activity, run anti-cheat cross-checks,
and push the result by email (and save it for the dashboard)."""
from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from .state import add_report, load_state, save_state


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sessions_on(state: dict[str, Any], day: str) -> list[dict[str, Any]]:
    out = []
    for s in state.get("sessions", []):
        started = s.get("started_at", "")[:10]
        if started == day:
            out.append(s)
    return out


def _exercises_on(state: dict[str, Any], day: str) -> list[dict[str, Any]]:
    out = []
    for ex_id, ex in state.get("exercises", {}).items():
        for a in ex.get("attempts", []):
            if a.get("at", "")[:10] == day:
                out.append({"id": ex_id, **a})
    return out


def _quizzes_on(state: dict[str, Any], day: str) -> list[dict[str, Any]]:
    out = []
    for q_id, q in state.get("quizzes", {}).items():
        if q.get("at", "")[:10] == day:
            out.append({"id": q_id, **q})
    return out


def build_report(cfg: dict[str, Any], day: str | None = None) -> dict[str, Any]:
    """Build the daily report dict with anti-cheat cross-checks."""
    day = day or _today()
    state = load_state()
    ac = cfg.get("anti_cheat", {})

    sessions = _sessions_on(state, day)
    exercises = _exercises_on(state, day)
    quizzes = _quizzes_on(state, day)

    logged_seconds = sum(s.get("duration_seconds", 0) for s in sessions)
    logged_hours = round(logged_seconds / 3600, 2)

    passed = [e for e in exercises if e.get("passed")]
    passed_with_solution = [e for e in exercises if e.get("passed_with_solution")]
    failed = [e for e in exercises if not e.get("passed") and not e.get("passed_with_solution")]
    quiz_avg = (
        round(sum(q["score"] / q["total"] for q in quizzes) / len(quizzes) * 100, 1)
        if quizzes else None
    )

    # ---- Anti-cheat cross-checks ----
    flags: list[str] = []

    if logged_hours > 0 and len(exercises) < ac.get("min_exercises_per_hour", 0.5) * logged_hours:
        flags.append(
            f"Low output: {len(exercises)} exercise attempt(s) for {logged_hours}h logged. "
            "Time and work don't match."
        )
    if logged_hours == 0 and (exercises or quizzes):
        flags.append("Work recorded but no session was logged (session_logger not run?).")
    for e in exercises:
        if e.get("similarity", 0) > ac.get("similarity_threshold", 0.85):
            flags.append(
                f"Exercise '{e['id']}' is {round(e['similarity']*100)}% similar to the "
                "reference solution — possible copy."
            )
    for s in sessions:
        try:
            start_hour = datetime.fromisoformat(s["started_at"]).hour
            if start_hour < ac.get("late_night_end", 5):
                flags.append(f"A session started at {s['started_at']} (late night).")
        except Exception:
            pass

    report = {
        "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "learner": cfg.get("learner", {}).get("name", "Fresher"),
        "current_day": state.get("current_day"),
        "logged_hours": logged_hours,
        "sessions": len(sessions),
        "exercises_attempted": len(exercises),
        "exercises_passed": len(passed),
        "exercises_passed_with_solution": len(passed_with_solution),
        "exercises_failed": len(failed),
        "quizzes_taken": len(quizzes),
        "quiz_avg_percent": quiz_avg,
        "flags": flags,
        "cheat_risk": "high" if len(flags) >= 2 else ("medium" if flags else "low"),
        "details": {
            "exercises": exercises,
            "quizzes": quizzes,
            "sessions": [
                {k: s[k] for k in ("started_at", "ended_at", "duration_seconds") if k in s}
                for s in sessions
            ],
        },
    }

    add_report(state, report)
    save_state(state)
    return report


def format_report_text(report: dict[str, Any]) -> str:
    lines = [
        f"=== Daily Study Report — {report['date']} ===",
        f"Learner: {report['learner']}   (curriculum day {report['current_day']})",
        "",
        f"Logged study time : {report['logged_hours']} h  ({report['sessions']} session(s))",
        f"Exercises         : {report['exercises_passed']} passed, "
        f"{report['exercises_passed_with_solution']} passed with solution, "
        f"{report['exercises_failed']} failed  (of {report['exercises_attempted']} attempted)",
        f"Quizzes           : {report['quizzes_taken']} taken"
        + (f", average {report['quiz_avg_percent']}%" if report["quiz_avg_percent"] is not None else ""),
        "",
        f"Cheat risk: {report['cheat_risk'].upper()}",
    ]
    if report["flags"]:
        lines.append("Flags:")
        lines += [f"  - {f}" for f in report["flags"]]
    else:
        lines.append("No anomalies detected.")
    return "\n".join(lines)


def send_email(cfg: dict[str, Any], report: dict[str, Any]) -> bool:
    email = cfg.get("email", {})
    if not email.get("enabled"):
        print("Email disabled in config.yaml — skipping.")
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[cpp-mentor] Daily report {report['date']} — risk: {report['cheat_risk']}"
        msg["From"] = email.get("from", email.get("username"))
        msg["To"] = email.get("to", email.get("username"))
        msg.set_content(format_report_text(report))
        with smtplib.SMTP(email.get("smtp_host", "smtp.gmail.com"),
                          int(email.get("smtp_port", 587))) as server:
            server.starttls()
            server.login(email["username"], email["password"])
            server.send_message(msg)
        print("Report emailed.")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False


def run_report(cfg: dict[str, Any], day: str | None = None, send: bool = True) -> dict[str, Any]:
    report = build_report(cfg, day)
    print(format_report_text(report))
    if send:
        send_email(cfg, report)
    return report
