"""The teaching agent CLI.

Commands:
    python -m cpp_mentor study            # interactive Gemini teaching session for today
    python -m cpp_mentor exercise         # generate a fresh exercise for the current topic
    python -m cpp_mentor submit <id>      # verify your solution file for an exercise
    python -m cpp_mentor quiz             # take a short quiz on the current topic
    python -m cpp_mentor status           # show progress
    python -m cpp_mentor next             # mark today done, move to the next day
    python -m cpp_mentor report [--send]  # build (and email) the daily report

Inside `study`, type /exercise, /quiz, /next, /done, /help, or /quit.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import state as st
from .config import load_config
from .exercises_gen import generate_exercise, generate_quiz
from .gemini_client import GeminiError, chat
from .report import run_report
from .verify import verify_code, load_exercises

# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------

def _progress_summary(state: dict[str, Any], curriculum: dict[str, Any]) -> str:
    day = st.get_day(curriculum, state.get("current_day", 1))
    if not day:
        return "No current day."
    lines = [f"Today is curriculum day {day['day']}:"]
    for t in day.get("topics", []):
        status = st.topic_status(state, t["id"])
        lines.append(f"  - [{status}] {t['title']}")
    return "\n".join(lines)


def _phase_overview(curriculum: dict[str, Any]) -> str:
    phases = curriculum.get("phases", [])
    if phases:
        return "\n".join(f"  - {p['name']} (days {p['days']})" for p in phases)
    return "  (see day list)"


def _system_prompt(cfg: dict[str, Any], state: dict[str, Any],
                   curriculum: dict[str, Any]) -> str:
    learner = cfg.get("learner", {}).get("name", "the learner")
    day = st.get_day(curriculum, state.get("current_day", 1))
    phase = day.get("phase", "") if day else ""
    return f"""You are an expert, patient C and C++ mentor teaching {learner}, a complete fresher.

The course is a 90-day plan. The learner studies 1 to 1.5 hours per day, so each
day has only ONE or TWO small topics. Go slow and make sure each concept is truly
understood before moving on — depth over speed.

Your teaching rules:
1. Teach ONE small concept at a time. Explain it clearly and simply, in plain language.
2. Always show a short, correct code example after explaining.
3. After each concept, ask the learner a quick check question to confirm understanding.
4. If the learner is confused, re-explain from a different angle — do not move on.
5. Be encouraging but honest. Point out mistakes clearly.
6. Focus on today's topics only. Do not skip ahead or cram multiple topics.
7. When a topic is well understood, tell the learner to run `/exercise` to practice it.
8. Keep replies focused and not too long (under ~300 words unless explaining code).

Course phases:
{_phase_overview(curriculum)}

Today is day {day.get('day') if day else '?'} (phase: {phase or 'n/a'}).
Current progress:
{_progress_summary(state, curriculum)}

You may use these slash commands (the learner types them, you do not):
/exercise  /quiz  /next  /done  /status  /help  /quit
"""


# ---------------------------------------------------------------------------
# Interactive study loop
# ---------------------------------------------------------------------------

def cmd_study(cfg: dict[str, Any]) -> None:
    state = st.load_state()
    curriculum = st.load_curriculum()
    system = _system_prompt(cfg, state, curriculum)
    history: list[dict[str, str]] = []

    day = st.get_day(curriculum, state.get("current_day", 1))
    print(f"=== Study session — Day {day['day'] if day else '?'} ===")
    print("Type /help for commands. /quit to exit.\n")

    greeting = (
        f"Welcome back, {cfg.get('learner', {}).get('name', 'learner')}! "
        f"Here's where we are: {_progress_summary(state, curriculum)}\n\n"
        "What would you like to work on today?"
    )
    print("MENTOR:", greeting, "\n")
    history.append({"role": "model", "content": greeting})

    while True:
        try:
            user = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break
        if not user:
            continue

        if user.startswith("/"):
            action = _handle_slash(user, cfg, state, curriculum, history)
            if action == "quit":
                break
            if action == "continue":
                continue
            # other slash commands mutate state; refresh system prompt
            system = _system_prompt(cfg, state, curriculum)
            continue

        try:
            reply = chat(cfg, system, history, user)
        except GeminiError as e:
            print("ERROR:", e)
            continue
        print("\nMENTOR:", reply, "\n")
        history.append({"role": "user", "content": user})
        history.append({"role": "model", "content": reply})
        # keep history bounded
        if len(history) > 40:
            history = history[-40:]

    st.save_state(state)


def _current_topic(state: dict[str, Any], curriculum: dict[str, Any]) -> dict[str, Any] | None:
    day = st.get_day(curriculum, state.get("current_day", 1))
    if not day:
        return None
    for t in day.get("topics", []):
        if st.topic_status(state, t["id"]) != "completed":
            return t
    return day.get("topics", [{}])[0] or None


def _handle_slash(user: str, cfg: dict[str, Any], state: dict[str, Any],
                  curriculum: dict[str, Any], history: list[dict[str, str]]) -> str:
    cmd = user.split()[0].lower()
    if cmd == "/quit":
        print("Session ended. Progress saved.")
        return "quit"
    if cmd == "/help":
        print("/exercise  generate & practice a coding exercise for the current topic")
        print("/quiz      take a short quiz on the current topic")
        print("/next      mark today complete and move to the next day")
        print("/done      mark the current topic complete")
        print("/status    show progress")
        print("/quit      exit the session")
        return "continue"
    if cmd == "/status":
        print(_progress_summary(state, curriculum))
        return "continue"
    if cmd == "/exercise":
        _do_exercise(cfg, state, curriculum)
        return "continue"
    if cmd == "/quiz":
        _do_quiz(cfg, state, curriculum)
        return "continue"
    if cmd == "/done":
        topic = _current_topic(state, curriculum)
        if topic:
            st.set_topic_status(state, topic["id"], "completed")
            st.save_state(state)
            print(f"Marked '{topic['title']}' as completed.")
        return "continue"
    if cmd == "/next":
        _advance_day(state, curriculum)
        return "continue"
    print("Unknown command. Type /help.")
    return "continue"


def _advance_day(state: dict[str, Any], curriculum: dict[str, Any]) -> None:
    days = [d["day"] for d in curriculum.get("days", [])]
    cur = state.get("current_day", 1)
    if cur in days and cur + 1 in days:
        state["current_day"] = cur + 1
        st.save_state(state)
        print(f"Moved to day {cur + 1}.")
    else:
        print("Already on the last day of the curriculum. Congratulations!")


# ---------------------------------------------------------------------------
# Exercise flow
# ---------------------------------------------------------------------------

def _exercise_language(state: dict[str, Any], curriculum: dict[str, Any]) -> str:
    """Pick the exercise language from the current day's phase.

    Phase 1 (C Fundamentals) uses C; every later phase uses C++.
    """
    day = st.get_day(curriculum, state.get("current_day", 1))
    phase = (day or {}).get("phase", "")
    return "c" if phase.startswith("C Fundamentals") else "cpp"


def _do_exercise(cfg: dict[str, Any], state: dict[str, Any], curriculum: dict[str, Any]) -> None:
    topic = _current_topic(state, curriculum)
    if not topic:
        print("No topic available.")
        return
    lang = _exercise_language(state, curriculum)
    print(f"Generating a fresh exercise for: {topic['title']} ({lang})...")
    try:
        ex = generate_exercise(cfg, topic, language=lang)
    except (GeminiError, ValueError) as e:
        print("Could not generate exercise:", e)
        return
    ex["topic_id"] = topic["id"]
    ex["generated_at"] = datetime.now(timezone.utc).isoformat()
    _save_exercise(ex)
    print("\n" + "=" * 60)
    print(f"EXERCISE: {ex['title']}")
    print("=" * 60)
    print(ex["prompt"])
    print("=" * 60)
    sol_path = st.work_path(ex["id"], f"solution.{ 'cpp' if lang=='cpp' else 'c' }")
    print(f"\nWrite your {lang} solution to: {sol_path}")
    print(f"Then run:  python -m cpp_mentor submit {ex['id']}")


def _save_exercise(ex: dict[str, Any]) -> None:
    st.ensure_dirs()
    path = st.WORK_DIR / f"{ex['id']}.json"
    path.write_text(json.dumps(ex, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_exercise(cfg: dict[str, Any]) -> None:
    state = st.load_state()
    curriculum = st.load_curriculum()
    _do_exercise(cfg, state, curriculum)


def cmd_submit(cfg: dict[str, Any], exercise_id: str) -> None:
    state = st.load_state()
    ex_path = st.WORK_DIR / f"{exercise_id}.json"
    if not ex_path.exists():
        # Maybe it's in the static bank.
        bank = load_exercises()
        ex = bank.get(exercise_id)
        if not ex:
            print(f"Exercise '{exercise_id}' not found. Run `exercise` first to generate one.")
            return
    else:
        ex = json.loads(ex_path.read_text(encoding="utf-8"))

    lang = ex.get("language", "c")
    suffix = "cpp" if lang == "cpp" else "c"
    sol_path = st.work_path(exercise_id, f"solution.{suffix}")
    if not sol_path.exists():
        print(f"Solution file not found: {sol_path}")
        print(f"Write your {lang} code there, then run submit again.")
        return
    source = sol_path.read_text(encoding="utf-8")

    print("Compiling and testing your solution...")
    result = verify_code(cfg, ex, source, sol_path)

    ac = cfg.get("anti_cheat", {})
    max_attempts = int(ac.get("max_attempts", 3))
    prior = len(state["exercises"].get(exercise_id, {}).get("attempts", []))

    if result.passed:
        status = "passed"
    elif prior + 1 >= max_attempts:
        status = "passed_with_solution"
    else:
        status = "failed"

    attempt = {
        "at": datetime.now(timezone.utc).isoformat(),
        "compiled": result.compiled,
        "passed": result.passed,
        "passed_with_solution": status == "passed_with_solution",
        "similarity": result.similarity,
        "tests": result.to_dict()["tests"],
    }
    st.record_attempt(state, exercise_id, attempt)
    st.save_state(state)

    print("\n" + "=" * 60)
    if not result.compiled:
        print("RESULT: did not compile.")
        print(result.compile_output)
    else:
        print(f"RESULT: {result.passed_count}/{len(result.tests)} tests passed.")
        for t in result.tests:
            mark = "PASS" if t.passed else "FAIL"
            print(f"  [{mark}] {t.name}" + (f" — {t.detail}" if t.detail else ""))
    if result.similarity > 0:
        print(f"Similarity to reference solution: {round(result.similarity*100)}%")
    print("=" * 60)

    if status == "passed":
        print("Great work! Topic is solid. Try /quiz or move on.")
    elif status == "passed_with_solution":
        print("You've used your attempts — here's the reference solution to study:")
        print(ex.get("reference_solution", "(no reference available)"))
        print("Mark it understood, then continue.")
    else:
        print(f"You have {max_attempts - prior - 1} attempt(s) left. Debug and resubmit.")


# ---------------------------------------------------------------------------
# Quiz flow
# ---------------------------------------------------------------------------

def _do_quiz(cfg: dict[str, Any], state: dict[str, Any], curriculum: dict[str, Any]) -> None:
    topic = _current_topic(state, curriculum)
    if not topic:
        print("No topic available.")
        return
    count = int(topic.get("quiz_count", 3) or 3)
    print(f"Generating a {count}-question quiz for: {topic['title']}...")
    try:
        quiz = generate_quiz(cfg, topic, count=count)
    except (GeminiError, ValueError) as e:
        print("Could not generate quiz:", e)
        return
    if not quiz:
        print("Quiz came back empty. Try again.")
        return

    print("\n" + "=" * 60)
    for i, q in enumerate(quiz, 1):
        print(f"\nQ{i}. {q['question']}")
        for j, opt in enumerate(q.get("options", []), 1):
            print(f"   {j}) {opt}")
    print("\n" + "=" * 60)
    print("Enter your answers as space-separated numbers, e.g.  1 3 2 4")
    try:
        raw = input("YOUR ANSWERS: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nQuiz cancelled.")
        return
    answers = [int(x) - 1 for x in raw.split() if x.strip().isdigit()]

    score = 0
    print("\n--- Results ---")
    for i, q in enumerate(quiz):
        correct = q.get("answer")
        given = answers[i] if i < len(answers) else None
        ok = given == correct
        if ok:
            score += 1
        opts = q.get("options", [])
        print(f"Q{i+1}: {'correct' if ok else 'wrong'}"
              f"  (you: {given+1 if given is not None and given>=0 else '-'}, "
              f"answer: {correct+1})")
        if not ok:
            print(f"   {q.get('explanation','').strip()}")

    quiz_id = f"{topic['id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    st.record_quiz(state, quiz_id, score, len(quiz))
    st.save_state(state)
    print(f"\nScore: {score}/{len(quiz)} ({round(score/len(quiz)*100)}%)")


def cmd_quiz(cfg: dict[str, Any]) -> None:
    state = st.load_state()
    curriculum = st.load_curriculum()
    _do_quiz(cfg, state, curriculum)


# ---------------------------------------------------------------------------
# Status / report / next
# ---------------------------------------------------------------------------

def cmd_status(cfg: dict[str, Any]) -> None:
    state = st.load_state()
    curriculum = st.load_curriculum()
    print(f"Learner: {cfg.get('learner', {}).get('name')}")
    print(f"Current day: {state.get('current_day')} of "
          f"{len(curriculum.get('days', []))}")
    print()
    print(_progress_summary(state, curriculum))
    ex = state.get("exercises", {})
    passed = sum(1 for e in ex.values() if e.get("status") == "passed")
    pws = sum(1 for e in ex.values() if e.get("status") == "passed_with_solution")
    print(f"\nExercises: {passed} passed, {pws} passed-with-solution, "
          f"{len(ex) - passed - pws} in-progress/failed")
    quizzes = state.get("quizzes", {})
    if quizzes:
        avg = sum(q["score"]/q["total"] for q in quizzes.values())/len(quizzes)*100
        print(f"Quizzes: {len(quizzes)} taken, average {round(avg,1)}%")
    total_hours = sum(s.get("duration_seconds", 0) for s in state.get("sessions", []))/3600
    print(f"Total logged study time: {round(total_hours,2)} h")


def cmd_next(cfg: dict[str, Any]) -> None:
    state = st.load_state()
    curriculum = st.load_curriculum()
    _advance_day(state, curriculum)


def cmd_report(cfg: dict[str, Any], send: bool) -> None:
    run_report(cfg, send=send)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cpp_mentor", description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("study", help="interactive teaching session")
    sub.add_parser("exercise", help="generate a fresh exercise")
    p_submit = sub.add_parser("submit", help="verify a solution")
    p_submit.add_argument("id", help="exercise id")
    sub.add_parser("quiz", help="take a quiz")
    sub.add_parser("status", help="show progress")
    sub.add_parser("next", help="advance to the next day")
    p_report = sub.add_parser("report", help="build the daily report")
    p_report.add_argument("--send", action="store_true", help="also email it")
    sub.add_parser("selftest", help="check that everything is installed and working")

    args = parser.parse_args(argv)
    cfg = load_config()

    if args.cmd == "study":
        cmd_study(cfg)
    elif args.cmd == "exercise":
        cmd_exercise(cfg)
    elif args.cmd == "submit":
        cmd_submit(cfg, args.id)
    elif args.cmd == "quiz":
        cmd_quiz(cfg)
    elif args.cmd == "status":
        cmd_status(cfg)
    elif args.cmd == "next":
        cmd_next(cfg)
    elif args.cmd == "report":
        cmd_report(cfg, send=args.send)
    elif args.cmd == "selftest":
        from .selftest import main as selftest_main
        selftest_main()
    else:
        # Default: start a study session.
        parser.print_help()
        print("\nTip: run `python -m cpp_mentor study` to begin learning.")


if __name__ == "__main__":
    main()
