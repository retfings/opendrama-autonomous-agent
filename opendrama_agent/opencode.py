from __future__ import annotations
import requests
from requests.auth import HTTPBasicAuth


def _unwrap(data):
    """Unwrap OpenCode V2's {"data": ...} envelope."""
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return data


class OpenCodeClient:
    """Minimal OpenCode V2 HTTP API client.

    V2 serves the HTTP API under /api and returns most payloads inside a
    {"data": ...} envelope.  Authentication is HTTP Basic with the username
    "opencode" and the password from ~/.config/opencode/service.json.
    """

    def __init__(self, base_url: str, username: str | None = None, password: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.http = requests.Session()
        self.http.headers.update({"Accept": "application/json"})
        if username or password:
            self.http.auth = HTTPBasicAuth(username or "", password or "")
        self.http.timeout = 20

    def _request(self, method: str, path: str, **kwargs):
        response = self.http.request(method, self.base_url + path, timeout=kwargs.pop("timeout", 20), **kwargs)
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else response.text

    def health(self):
        # V1 used /global/health. V2 exposes server info at /api/info and has
        # no dedicated health endpoint.
        return self._request("GET", "/api/info")

    def sessions(self):
        data = _unwrap(self._request("GET", "/api/session", params={"limit": "500"}))
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected /api/session response: {type(data).__name__}")
        return data

    def _pending_user_input(self, session_id: str) -> bool:
        """Return True when an active session is blocked on a question/permission."""
        for path in (
            f"/api/session/{session_id}/form",
            f"/api/session/{session_id}/permission",
        ):
            try:
                data = _unwrap(self._request("GET", path))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                raise
            if isinstance(data, list) and data:
                return True
        return False

    def statuses(self):
        # V2 exposes only currently running sessions. An active session can be
        # either doing real work or waiting for a user answer/permission.
        active = _unwrap(self._request("GET", "/api/session/active"))
        if not isinstance(active, dict):
            raise RuntimeError(f"Unexpected /api/session/active response: {type(active).__name__}")
        result = {}
        for session in self.sessions():
            session_id = session.get("id")
            if not session_id:
                continue
            if session_id not in active:
                result[session_id] = {"type": "idle"}
            elif self._pending_user_input(session_id):
                result[session_id] = {"type": "waiting_for_user"}
            else:
                result[session_id] = {"type": "busy"}
        return result

    def create_session(self, title: str, directory=None, agent=None, model=None):
        body = {"title": title}
        if directory is not None:
            body["location"] = {"directory": str(directory)}
        if agent:
            body["agent"] = agent
        if model:
            body["model"] = model
        data = _unwrap(self._request("POST", "/api/session", json=body))
        if not isinstance(data, dict) or not data.get("id"):
            raise RuntimeError(f"Unexpected session creation response: {data!r}")
        return data

    def prompt_async(self, session_id: str, text: str):
        # V2 replaced /session/{id}/prompt_async with /api/session/{id}/prompt.
        return self._request(
            "POST",
            f"/api/session/{session_id}/prompt",
            json={"text": text},
            timeout=30,
        )

    def session_messages(self, session_id: str):
        data = _unwrap(self._request("GET", f"/api/session/{session_id}/message"))
        return data if isinstance(data, list) else []
