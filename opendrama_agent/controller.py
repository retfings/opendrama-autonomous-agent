from __future__ import annotations
import fcntl, json, logging, time, uuid
from pathlib import Path
from datetime import datetime
from .config import Config
from .opencode import OpenCodeClient
from .state import load, save, now
from .prompts import build_prompt

def _session_dir(session: dict) -> str | None:
    value = session.get("directory")
    return str(Path(value).resolve()) if value else None

def _belongs(session: dict, project: Path) -> bool:
    directory = _session_dir(session)
    return directory == str(project.resolve())

def project_sessions(client: OpenCodeClient, cfg: Config):
    sessions = client.sessions()
    statuses = client.statuses()
    matches = []
    unknown = []
    for session in sessions:
        directory = _session_dir(session)
        if directory is None:
            unknown.append(session.get("id", "<unknown>"))
            continue
        if _belongs(session, cfg.project_path):
            sid = session.get("id")
            status_obj = statuses.get(sid, {})
            status = status_obj.get("type", "unknown") if isinstance(status_obj, dict) else str(status_obj)
            matches.append({"id": sid, "title": session.get("title"), "status": status})
    if cfg.require_project_directory_match and unknown:
        raise RuntimeError(
            "Cannot safely determine project ownership for sessions without "
            f"directory metadata: {unknown}. Refusing to start another agent."
        )
    for item in matches:
        if item["status"] not in ("idle", "busy", "retry"):
            raise RuntimeError(
                f"Unknown OpenCode status for project session {item['id']}: "
                f"{item['status']!r}. Refusing to start another agent."
            )
    return matches

def _result_status(cfg: Config):
    path = cfg.project_path / cfg.result_file
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None

def _ensure_session(client, cfg, state):
    existing = {s.get("id"): s for s in client.sessions()}
    sid = state.get("session_id")
    if cfg.continue_previous_session and sid in existing and _belongs(existing[sid], cfg.project_path):
        return sid
    created = client.create_session(cfg.session_title)
    return created["id"]

def run(base: Path, cfg: Config):
    data_dir = base / "data"
    log_dir = base / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "scheduler.lock"
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            logging.info("Another scheduler process holds the lock; skipping.")
            return "skipped_locked"

        client = OpenCodeClient(cfg.opencode_url, cfg.username, cfg.password)
        health = client.health()
        if isinstance(health, dict) and health.get("healthy") is False:
            raise RuntimeError(f"OpenCode server unhealthy: {health}")

        sessions = project_sessions(client, cfg)
        busy = [s for s in sessions if s["status"] in ("busy", "retry")]
        if busy:
            logging.info("Project already has active LLM work; skipping: %s", busy)
            return "skipped_busy"

        state_path = data_dir / "state.json"
        state = load(state_path)
        task_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        sid = _ensure_session(client, cfg, state)
        state.update({"session_id": sid, "last_run": now(cfg.timezone),
                      "last_status": "running", "last_error": None, "task_id": task_id})
        save(state_path, state)

        result_path = cfg.project_path / cfg.result_file
        result_path.parent.mkdir(parents=True, exist_ok=True)
        if result_path.exists():
            result_path.unlink()

        prompt = build_prompt(cfg, task_id)
        client.prompt_async(sid, prompt)
        logging.info("Submitted task %s to session %s", task_id, sid)

        deadline = time.monotonic() + cfg.max_runtime_minutes * 60
        busy_seen = False
        idle_since = None
        while time.monotonic() < deadline:
            status_obj = client.statuses().get(sid, {})
            status = status_obj.get("type", "unknown") if isinstance(status_obj, dict) else str(status_obj)
            if status in ("busy", "retry"):
                busy_seen = True
                idle_since = None
            elif status == "idle":
                if busy_seen:
                    idle_since = idle_since or time.monotonic()
                    if time.monotonic() - idle_since >= cfg.completion_idle_seconds:
                        break
                else:
                    time.sleep(cfg.poll_interval_seconds)
            else:
                logging.warning("Unrecognized session status %r; continuing to observe.", status)
            time.sleep(cfg.poll_interval_seconds)

        final_status_obj = client.statuses().get(sid, {})
        final_status = final_status_obj.get("type", "unknown") if isinstance(final_status_obj, dict) else str(final_status_obj)
        result = _result_status(cfg)
        if final_status in ("busy", "retry"):
            state["last_status"] = "still_running"
        elif not busy_seen:
            state["last_status"] = "unconfirmed"
        elif result and result.get("task_id") == task_id and result.get("status") in ("completed", "partial", "blocked", "failed"):
            state["last_status"] = result["status"]
        else:
            state["last_status"] = "finished_without_valid_result"
        save(state_path, state)
        logging.info("Task %s ended with scheduler status %s; result=%s",
                     task_id, state["last_status"], result)
        return state["last_status"]
