from __future__ import annotations
import json
import os
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Config:
    project_path: Path
    opencode_url: str
    timezone: str
    poll_interval_seconds: int
    max_runtime_minutes: int
    completion_idle_seconds: int
    max_iterations: int
    continue_previous_session: bool
    session_title: str
    report_dir: str
    progress_file: str
    result_file: str
    require_project_directory_match: bool
    username: str | None
    password: str | None

def load_config(base: Path) -> Config:
    raw = json.loads((base / "config.json").read_text(encoding="utf-8"))
    project = Path(raw["project_path"]).expanduser().resolve()
    if not project.is_dir():
        raise RuntimeError(f"Project directory does not exist: {project}")
    return Config(
        project_path=project,
        opencode_url=raw["opencode_url"].rstrip("/"),
        timezone=raw.get("timezone", "Asia/Shanghai"),
        poll_interval_seconds=max(3, int(raw.get("poll_interval_seconds", 15))),
        max_runtime_minutes=max(1, int(raw.get("max_runtime_minutes", 540))),
        completion_idle_seconds=max(10, int(raw.get("completion_idle_seconds", 30))),
        max_iterations=max(1, int(raw.get("max_iterations", 4))),
        continue_previous_session=bool(raw.get("continue_previous_session", True)),
        session_title=raw.get("session_title", "OpenDrama Autonomous R&D"),
        report_dir=raw.get("report_dir", "reports/daily-research"),
        progress_file=raw.get("progress_file", ".automation/PROGRESS.md"),
        result_file=raw.get("result_file", ".automation/RESULT.json"),
        require_project_directory_match=bool(raw.get("require_project_directory_match", True)),
        username=os.getenv("OPENCODE_SERVER_USERNAME"),
        password=os.getenv("OPENCODE_SERVER_PASSWORD"),
    )
