"""Self-test: verify that every layer of cpp-mentor works on this machine.

Run:  python -m cpp_mentor selftest

Checks:
  1. Python version
  2. Required packages (yaml, google-genai, fastapi, uvicorn, jinja2)
  3. C and C++ compilers on PATH
  4. Gemini API key present (and optionally a live API ping)
  5. Curriculum & exercise bank load correctly
  6. End-to-end code verification: a correct program PASSES, a broken one FAILS
  7. Daily report builds without error

Exit code 0 = all good, 1 = something failed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PASS = "  [PASS]"
FAIL = "  [FAIL]"
WARN = "  [WARN]"

failures: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"{PASS} {msg}")


def bad(msg: str) -> None:
    print(f"{FAIL} {msg}")
    failures.append(msg)


def warn(msg: str) -> None:
    print(f"{WARN} {msg}")
    warnings.append(msg)


def check_python() -> None:
    print("\n== 1. Python ==")
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        bad(f"Python {v.major}.{v.minor}.{v.micro} — need 3.10 or newer")


def check_packages() -> None:
    print("\n== 2. Python packages ==")
    needed = {
        "yaml": "PyYAML",
        "google.genai": "google-genai",
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "jinja2": "Jinja2",
    }
    for module, pip_name in needed.items():
        try:
            __import__(module)
            ok(f"{pip_name} installed")
        except ImportError:
            bad(f"{pip_name} missing — run: pip install {pip_name}")


def check_compiler(cfg: dict, key: str, label: str) -> bool:
    comp = cfg.get("compiler", {}).get(key, "gcc")
    path = shutil.which(comp)
    if not path:
        bad(f"{label} compiler '{comp}' not found on PATH")
        return False
    try:
        out = subprocess.run([comp, "--version"], capture_output=True, text=True, timeout=15)
        first_line = (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else comp
        ok(f"{label} compiler: {first_line}")
        return True
    except Exception as e:
        bad(f"{label} compiler failed to run: {e}")
        return False


def check_compilers(cfg: dict) -> bool:
    print("\n== 3. Compilers ==")
    c_ok = check_compiler(cfg, "c", "C")
    cpp_ok = check_compiler(cfg, "cpp", "C++")
    return c_ok and cpp_ok


def check_gemini(cfg: dict, live: bool) -> bool:
    print("\n== 4. Gemini API ==")
    env = cfg.get("gemini", {}).get("api_key_env", "GEMINI_API_KEY")
    key = os.environ.get(env, "")
    if not key:
        bad(f"Environment variable {env} is not set")
        return False
    ok(f"{env} is set ({key[:6]}...{key[-4:]})")
    if not live:
        warn("Skipping live API call (use --live to test it)")
        return True
    try:
        from .gemini_client import chat
        reply = chat(cfg, "You are a test. Reply with exactly: OK", [], "ping")
        if "OK" in reply.upper():
            ok(f"Live API call succeeded (model: {cfg.get('gemini', {}).get('model')})")
            return True
        bad(f"Live API call returned unexpected reply: {reply[:80]}")
        return False
    except Exception as e:
        bad(f"Live API call failed: {e}")
        return False


def check_data(cfg: dict) -> None:
    print("\n== 5. Curriculum & exercises ==")
    from .state import load_curriculum
    try:
        cur = load_curriculum()
        days = cur.get("days", [])
        if len(days) == 90:
            ok(f"curriculum.json loads — {len(days)} days, "
               f"{len(cur.get('phases', []))} phases")
        else:
            warn(f"curriculum.json loads but has {len(days)} days (expected 90)")
    except Exception as e:
        bad(f"curriculum.json failed to load: {e}")
    try:
        from .verify import load_exercises
        ex = load_exercises()
        ok(f"exercises.json loads — {len(ex)} static exercises")
    except Exception as e:
        bad(f"exercises.json failed to load: {e}")


def check_verify(cfg: dict) -> bool:
    """End-to-end: a correct program must pass, a broken one must fail."""
    print("\n== 6. Code verification (end-to-end) ==")
    from .verify import verify_code

    good = {
        "language": "c",
        "tests": [{"name": "t1", "input": "3 4\n", "expected": "7"}],
        "reference_solution": "#include <stdio.h>\nint main(void){int a,b;scanf(\"%d %d\",&a,&b);printf(\"%d\\n\",a+b);return 0;}\n",
    }
    bad_prog = {
        "language": "c",
        "tests": [{"name": "t1", "input": "3 4\n", "expected": "7"}],
        "reference_solution": "",
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

        good_src = tmpdir / "good.c"
        good_src.write_text(
            "#include <stdio.h>\n"
            "int main(void){int a,b;scanf(\"%d %d\",&a,&b);printf(\"%d\\n\",a+b);return 0;}\n",
            encoding="utf-8",
        )
        r = verify_code(cfg, good, good_src.read_text(encoding="utf-8"), good_src)
        if r.compiled and r.passed:
            ok("Correct program compiles and PASSES tests")
        else:
            bad(f"Correct program should pass but got: compiled={r.compiled} "
                f"passed={r.passed} out={r.compile_output[:120]}")

        bad_src = tmpdir / "bad.c"
        bad_src.write_text(
            "#include <stdio.h>\n"
            "int main(void){int a,b;scanf(\"%d %d\",&a,&b);printf(\"%d\\n\",a-b);return 0;}\n",
            encoding="utf-8",
        )
        r2 = verify_code(cfg, bad_prog, bad_src.read_text(encoding="utf-8"), bad_src)
        if r2.compiled and not r2.passed:
            ok("Wrong program compiles but FAILS tests (as expected)")
        elif not r2.compiled:
            bad("Wrong program did not compile — compiler problem?")
        else:
            bad("Wrong program PASSED tests — verification is broken!")

        broken_src = tmpdir / "broken.c"
        broken_src.write_text("this is not C code at all", encoding="utf-8")
        r3 = verify_code(cfg, bad_prog, broken_src.read_text(encoding="utf-8"), broken_src)
        if not r3.compiled:
            ok("Broken source is correctly rejected at compile step")
        else:
            bad("Broken source compiled — verification is broken!")

    return not any("verification is broken" in f for f in failures)


def check_report(cfg: dict) -> None:
    print("\n== 7. Daily report ==")
    from .report import build_report, format_report_text
    try:
        rep = build_report(cfg)
        text = format_report_text(rep)
        if "Cheat risk" in text:
            ok(f"Report builds (risk: {rep['cheat_risk']}, "
               f"{rep['exercises_attempted']} exercise(s) on record)")
        else:
            bad("Report built but is missing the risk line")
    except Exception as e:
        bad(f"Report failed to build: {e}")


def main() -> None:
    print("=" * 60)
    print("cpp-mentor self-test")
    print("=" * 60)

    live = "--live" in sys.argv

    from .config import load_config
    try:
        cfg = load_config()
        ok("config.yaml loads")
    except Exception as e:
        bad(f"config.yaml failed to load: {e}")
        cfg = {}

    check_python()
    check_packages()
    compilers_ok = check_compilers(cfg)
    gemini_ok = check_gemini(cfg, live)
    check_data(cfg)
    check_verify(cfg)
    check_report(cfg)

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULT: {len(failures)} check(s) FAILED")
        for f in failures:
            print(f"  - {f}")
        print("\nFix the items above, then run selftest again.")
        sys.exit(1)
    else:
        print("RESULT: ALL CHECKS PASSED")
        if warnings:
            print(f"({len(warnings)} warning(s) — see above)")
        if not gemini_ok:
            print("Note: Gemini key not set — teaching will not work until you set it.")
        if not compilers_ok:
            print("Note: compiler missing — exercise verification will not work.")
        print("\nYou're ready. Start with:  python -m cpp_mentor study")
        sys.exit(0)


if __name__ == "__main__":
    main()
