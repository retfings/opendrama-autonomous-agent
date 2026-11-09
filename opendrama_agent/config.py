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
    agent: str | None = None
    model: dict | None = None
    block_on_waiting_user: bool = False
    wait_for_user_delay_minutes: int = 0
    wait_for_user_max_retries: int = 10
    wait_for_user_after_retries: str = "run"

def load_config(base: Path) -> Config:
    raw = json.loads((base / "config.json").read_text(encoding="utf-8"))
    project = Path(raw["project_path"]).expanduser().resolve()
    if not project.is_dir():
        raise RuntimeError(f"Project directory does not exist: {project}")
    after_retries = str(raw.get("wait_for_user_after_retries", "run")).lower()
    if after_retries not in ("run", "skip"):
        raise RuntimeError(
            "wait_for_user_after_retries must be 'run' or 'skip', "
            f"got {after_retries!r}"
        )
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
        agent=raw.get("agent"),
        model=raw.get("model"),
        block_on_waiting_user=bool(raw.get("block_on_waiting_user", False)),
        wait_for_user_delay_minutes=max(0, int(raw.get("wait_for_user_delay_minutes", 0))),
        wait_for_user_max_retries=max(0, int(raw.get("wait_for_user_max_retries", 10))),
        wait_for_user_after_retries=after_retries,
    )
