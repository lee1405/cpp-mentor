"""Web dashboard for monitoring the fresher's progress.

Run:  python -m cpp_mentor.dashboard
Then open http://127.0.0.1:8000

Shows: daily study hours, exercises passed, quiz averages, cheat-risk flags,
and the current curriculum position. Data comes from data/state.json and
data/reports/*.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import REPORTS_DIR, load_config
from .state import load_curriculum, load_state

app = FastAPI(title="cpp-mentor dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _reports() -> list[dict]:
    out = []
    if REPORTS_DIR.exists():
        for f in sorted(REPORTS_DIR.glob("report_*.json")):
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
    return out


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = load_config()
    state = load_state()
    curriculum = load_curriculum()
    reports = _reports()
    # Merge in any reports stored in state that aren't on disk yet.
    seen = {r.get("date") for r in reports}
    for r in state.get("reports", []):
        if r.get("date") not in seen:
            reports.append(r)
    reports.sort(key=lambda r: r.get("date", ""))

    total_hours = sum(r.get("logged_hours", 0) for r in reports)
    total_passed = sum(r.get("exercises_passed", 0) for r in reports)
    flagged_days = [r for r in reports if r.get("flags")]
    latest = reports[-1] if reports else None

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "learner": cfg.get("learner", {}).get("name", "Fresher"),
            "current_day": state.get("current_day"),
            "total_days": len(curriculum.get("days", [])),
            "reports": reports,
            "total_hours": round(total_hours, 2),
            "total_passed": total_passed,
            "flagged_days": flagged_days,
            "latest": latest,
        },
    )


@app.get("/api/reports")
async def api_reports():
    return json.dumps(_reports())


def main() -> None:
    import uvicorn

    cfg = load_config()
    dash = cfg.get("dashboard", {})
    host = dash.get("host", "127.0.0.1")
    port = int(dash.get("port", 8000))
    print(f"Dashboard running at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
