from __future__ import annotations
import requests
from requests.auth import HTTPBasicAuth

class OpenCodeClient:
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
        return self._request("GET", "/global/health")

    def sessions(self):
        data = self._request("GET", "/session")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected /session response: {type(data).__name__}")
        return data

    def statuses(self):
        data = self._request("GET", "/session/status")
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected /session/status response: {type(data).__name__}")
        return data

    def create_session(self, title: str):
        data = self._request("POST", "/session", json={"title": title})
        if not isinstance(data, dict) or not data.get("id"):
            raise RuntimeError(f"Unexpected session creation response: {data!r}")
        return data

    def prompt_async(self, session_id: str, text: str):
        return self._request(
            "POST",
            f"/session/{session_id}/prompt_async",
            json={"parts": [{"type": "text", "text": text}]},
            timeout=30,
        )

    def session_messages(self, session_id: str):
        data = self._request("GET", f"/session/{session_id}/message")
        return data if isinstance(data, list) else []
