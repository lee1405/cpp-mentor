"""Anti-cheat verification: compile & run the learner's code against hidden
test cases, and compare similarity to the reference solution.

This is the strongest anti-cheat layer: a program either compiles and passes
the tests, or it does not. You cannot fake a passing binary.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import WORK_DIR


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyResult:
    compiled: bool
    compile_output: str = ""
    tests: list[TestResult] = field(default_factory=list)
    similarity: float = 0.0
    passed: bool = False

    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.tests if t.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiled": self.compiled,
            "compile_output": self.compile_output[-2000:],
            "tests": [
                {"name": t.name, "passed": t.passed, "detail": t.detail[:500]}
                for t in self.tests
            ],
            "similarity": round(self.similarity, 3),
            "passed": self.passed,
        }


def _normalize(code: str) -> str:
    """Normalize source for similarity comparison: strip comments, collapse
    whitespace, and rename identifiers so trivial renaming doesn't fool it."""
    code = re.sub(r"//.*", "", code)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    code = re.sub(r"#[^\n]*", "", code)
    code = re.sub(r"\s+", " ", code).strip()
    # Rename identifiers to a canonical form (catches variable renaming).
    idents = sorted(set(re.findall(r"[A-Za-z_]\w*", code)), key=len, reverse=True)
    mapping: dict[str, str] = {}
    for i, ident in enumerate(idents):
        if ident not in mapping:
            mapping[ident] = f"v{i}"
    for ident, canon in mapping.items():
        code = re.sub(rf"\b{re.escape(ident)}\b", canon, code)
    return code


def similarity(a: str, b: str) -> float:
    """0..1 similarity between two source files (normalized)."""
    if not a.strip() or not b.strip():
        return 0.0
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _run(cmd: list[str], cwd: Path, timeout: int, stdin: str | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return -2, f"compiler not found: {e}"


def verify_code(
    cfg: dict[str, Any],
    exercise: dict[str, Any],
    source: str,
    source_path: Path,
) -> VerifyResult:
    """Compile the learner's source and run it against the exercise's tests.

    exercise schema:
      {
        "language": "c" | "cpp",
        "tests": [{"name": ..., "input": "...", "expected": "..."}],
        "reference_solution": "..."   # optional, used for similarity check
      }
    """
    lang = exercise.get("language", "c")
    comp = cfg.get("compiler", {})
    compiler = comp.get("cpp" if lang == "cpp" else "c", "g++" if lang == "cpp" else "gcc")
    flags = comp.get("cppflags" if lang == "cpp" else "cflags", "")
    compile_timeout = int(comp.get("compile_timeout_seconds", 60))
    run_timeout = int(comp.get("run_timeout_seconds", 10))

    ext = ".cpp" if lang == "cpp" else ".c"
    exe_name = "solution" + (".exe" if os.name == "nt" else "")

    with tempfile.TemporaryDirectory(prefix="cppmentor_") as tmp:
        tmpdir = Path(tmp)
        src_file = tmpdir / ("solution" + ext)
        src_file.write_text(source, encoding="utf-8")

        compile_cmd = [compiler, *flags.split(), str(src_file), "-o", exe_name]
        rc, out = _run(compile_cmd, tmpdir, compile_timeout)
        if rc != 0:
            return VerifyResult(compiled=False, compile_output=out.strip())

        tests: list[TestResult] = []
        for t in exercise.get("tests", []):
            rc, out = _run([exe_name], tmpdir, run_timeout, stdin=t.get("input", ""))
            expected = t.get("expected", "").strip()
            actual = out.strip()
            passed = rc == 0 and actual == expected
            detail = "" if passed else f"expected={expected!r} actual={actual!r} rc={rc}"
            tests.append(TestResult(name=t.get("name", "test"), passed=passed, detail=detail))

    sim = 0.0
    ref = exercise.get("reference_solution", "")
    if ref:
        sim = similarity(source, ref)

    all_passed = bool(tests) and all(t.passed for t in tests)
    return VerifyResult(
        compiled=True,
        tests=tests,
        similarity=sim,
        passed=all_passed,
    )


def load_exercises() -> dict[str, dict[str, Any]]:
    """Load the exercise bank (exercises.json) keyed by exercise id."""
    path = WORK_DIR.parent.parent / "exercises.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {e["id"]: e for e in data.get("exercises", [])}
