"""Configuration loading and project paths."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
WORK_DIR = DATA_DIR / "work"
REPORTS_DIR = DATA_DIR / "reports"


def ensure_dirs() -> None:
    for d in (DATA_DIR, WORK_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else PROJECT_ROOT / "config.yaml"
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    ensure_dirs()
    return cfg
