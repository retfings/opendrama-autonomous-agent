import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

from opendrama_agent.controller import (
    _belongs,
    _ensure_session,
    _session_dir,
    project_sessions,
    run,
)


class ControllerV2SessionLocationTest(unittest.TestCase):
    def test_v2_location_directory_is_used(self):
        session = {"id": "ses_1", "location": {"directory": "/tmp/project"}}
        self.assertEqual(_session_dir(session), str(Path("/tmp/project").resolve()))

    def test_v1_top_level_directory_still_works(self):
        session = {"id": "ses_1", "directory": "/tmp/project"}
        self.assertEqual(_session_dir(session), str(Path("/tmp/project").resolve()))

    def test_belongs_compares_resolved_directories(self):
        session = {"id": "ses_1", "location": {"directory": "/tmp/project"}}
        self.assertTrue(_belongs(session, Path("/tmp/project")))
        self.assertFalse(_belongs(session, Path("/tmp/other")))


class FakeClient:
    def __init__(self, sessions, statuses):
        self._sessions = sessions
        self._statuses = statuses
        self.created = []

    def sessions(self):
        return self._sessions

    def statuses(self):
        return self._statuses

    def create_session(self, title, directory=None, agent=None, model=None):
        self.created.append(
            {"title": title, "directory": directory, "agent": agent, "model": model}
        )
        return {"id": "ses_new"}


def config(**overrides):
    values = {
        "project_path": Path("/tmp/project"),
        "require_project_directory_match": True,
        "continue_previous_session": True,
        "session_title": "test",
        "agent": "build",
        "model": None,
        "block_on_waiting_user": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeRunClient:
    def __init__(self, directory, waiting_checks=1):
        self.created = False
        self.prompted = False
        self.status_calls = 0
        self.waiting_checks = waiting_checks
        self.waiting_status_calls = 0
        self.waiting = {
            "id": "ses_waiting",
            "title": "waiting",
            "status": "waiting_for_user",
            "location": {"directory": str(directory)},
        }
        self.new = {
            "id": "ses_new",
            "title": "new",
            "location": {"directory": str(directory)},
        }

    def health(self):
        return {}

    def sessions(self):
        return [self.waiting, self.new] if self.created else [self.waiting]

    def statuses(self):
        if not self.created:
            self.waiting_status_calls += 1
            if self.waiting_status_calls <= self.waiting_checks:
                return {"ses_waiting": {"type": "waiting_for_user"}}
            return {"ses_waiting": {"type": "idle"}}
        self.status_calls += 1
        new_status = "busy" if self.status_calls == 1 else "idle"
        return {
            "ses_waiting": {"type": "waiting_for_user"},
            "ses_new": {"type": new_status},
        }

    def create_session(self, title, directory=None, agent=None, model=None):
        self.created = True
        return self.new

    def prompt_async(self, session_id, text):
        self.prompted = True
        return None


def run_config(project, **overrides):
    values = {
        "project_path": project,
        "opencode_url": "http://fake",
        "timezone": "Asia/Shanghai",
        "poll_interval_seconds": 0,
        "max_runtime_minutes": 1,
        "completion_idle_seconds": 0,
        "max_iterations": 1,
        "continue_previous_session": True,
        "session_title": "test",
        "report_dir": "reports/daily-research",
        "progress_file": ".automation/PROGRESS.md",
        "result_file": ".automation/RESULT.json",
        "require_project_directory_match": True,
        "username": None,
        "password": None,
        "agent": None,
        "model": None,
        "block_on_waiting_user": False,
        "wait_for_user_delay_minutes": 0,
        "wait_for_user_max_retries": 10,
        "wait_for_user_after_retries": "run",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ControllerWaitingForUserTest(unittest.TestCase):
    def test_project_sessions_accepts_waiting_for_user(self):
        client = FakeClient(
            [
                {"id": "ses_waiting", "location": {"directory": "/tmp/project"}},
                {"id": "ses_busy", "location": {"directory": "/tmp/project"}},
                {"id": "ses_idle", "location": {"directory": "/tmp/project"}},
            ],
            {
                "ses_waiting": {"type": "waiting_for_user"},
                "ses_busy": {"type": "busy"},
                "ses_idle": {"type": "idle"},
            },
        )
        matches = project_sessions(client, config())
        self.assertEqual(
            {item["id"]: item["status"] for item in matches},
            {
                "ses_waiting": "waiting_for_user",
                "ses_busy": "busy",
                "ses_idle": "idle",
            },
        )

    def test_previous_waiting_session_is_not_reused(self):
        client = FakeClient([], {})
        created = _ensure_session(
            client,
            config(),
            {"session_id": "ses_waiting"},
            [{"id": "ses_waiting", "status": "waiting_for_user"}],
        )
        self.assertEqual(created, "ses_new")
        self.assertEqual(len(client.created), 1)

    def test_previous_idle_session_is_reused(self):
        client = FakeClient([], {})
        created = _ensure_session(
            client,
            config(),
            {"session_id": "ses_idle"},
            [{"id": "ses_idle", "status": "idle"}],
        )
        self.assertEqual(created, "ses_idle")
        self.assertEqual(client.created, [])


class ControllerRunWaitingForUserTest(unittest.TestCase):
    def _run(self, project, waiting_checks=1, **overrides):
        fake = FakeRunClient(project, waiting_checks=waiting_checks)
        with patch("opendrama_agent.controller.OpenCodeClient", return_value=fake), \
             patch("opendrama_agent.controller.time.sleep") as sleep:
            result = run(Path(tempfile.mkdtemp()), run_config(project, **overrides))
        return fake, result, sleep

    def test_run_continues_when_other_session_waits_for_user(self):
        with tempfile.TemporaryDirectory() as project:
            fake, result, _ = self._run(Path(project))
            self.assertTrue(fake.created)
            self.assertTrue(fake.prompted)
            self.assertNotIn(result, ("skipped_busy", "skipped_waiting_user"))

    def test_run_can_block_on_waiting_user_when_configured(self):
        with tempfile.TemporaryDirectory() as project:
            fake, result, _ = self._run(
                Path(project), block_on_waiting_user=True
            )
            self.assertEqual(result, "skipped_waiting_user")
            self.assertFalse(fake.prompted)

    def test_run_waits_and_retries_then_proceeds(self):
        with tempfile.TemporaryDirectory() as project:
            fake, result, sleep = self._run(
                Path(project),
                waiting_checks=1,
                wait_for_user_delay_minutes=30,
                wait_for_user_max_retries=3,
                wait_for_user_after_retries="run",
            )
            self.assertIn(call(30 * 60), sleep.call_args_list)
            self.assertTrue(fake.prompted)
            self.assertNotIn(result, ("skipped_busy", "skipped_waiting_user"))

    def test_run_waits_max_retries_then_skips(self):
        with tempfile.TemporaryDirectory() as project:
            fake, result, sleep = self._run(
                Path(project),
                waiting_checks=999,
                wait_for_user_delay_minutes=30,
                wait_for_user_max_retries=2,
                wait_for_user_after_retries="skip",
            )
            self.assertEqual(result, "skipped_waiting_user")
            self.assertFalse(fake.prompted)
            self.assertEqual(
                [c for c in sleep.call_args_list if c == call(30 * 60)],
                [call(30 * 60), call(30 * 60)],
            )

    def test_run_waits_max_retries_then_runs(self):
        with tempfile.TemporaryDirectory() as project:
            fake, result, sleep = self._run(
                Path(project),
                waiting_checks=999,
                wait_for_user_delay_minutes=30,
                wait_for_user_max_retries=2,
                wait_for_user_after_retries="run",
            )
            self.assertTrue(fake.prompted)
            self.assertNotIn(result, ("skipped_busy", "skipped_waiting_user"))
            self.assertEqual(
                [c for c in sleep.call_args_list if c == call(30 * 60)],
                [call(30 * 60), call(30 * 60)],
            )


if __name__ == "__main__":
    unittest.main()
