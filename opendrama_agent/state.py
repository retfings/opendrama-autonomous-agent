from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT = {
    "session_id": None,
    "last_run": None,
    "last_status": "idle",
    "last_error": None,
    "task_id": None,
}

def load(path: Path):
    if not path.exists():
        return DEFAULT.copy()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {**DEFAULT, **data}

def save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)

def now(tz: str):
    return datetime.now(ZoneInfo(tz)).isoformat()
