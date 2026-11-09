import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opendrama_agent.opencode import OpenCodeClient

USER = "opencode"
PASSWORD = "test-password"
AUTH = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()

SESSIONS = [
    {
        "id": "ses_busy",
        "projectID": "prj_1",
        "cost": 0,
        "tokens": {},
        "time": {"created": 1, "updated": 2},
        "title": "active work",
        "location": {"directory": "/tmp/project"},
    },
    {
        "id": "ses_waiting",
        "projectID": "prj_1",
        "cost": 0,
        "tokens": {},
        "time": {"created": 1, "updated": 2},
        "title": "waiting for user",
        "location": {"directory": "/tmp/project"},
    },
    {
        "id": "ses_idle",
        "projectID": "prj_1",
        "cost": 0,
        "tokens": {},
        "time": {"created": 1, "updated": 2},
        "title": "idle work",
        "location": {"directory": "/tmp/project"},
    },
]


class Handler(BaseHTTPRequestHandler):
    prompt_body = None
    create_body = None

    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        if self.headers.get("Authorization") != AUTH:
            self._send(401, {"_tag": "UnauthorizedError", "message": "Authentication required"})
            return False
        return True

    def do_GET(self):
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/info":
            self._send(200, {"version": "2.2.5", "pid": 1, "urls": [], "paths": {"tmp": "/tmp"}})
        elif path == "/api/session":
            self._send(200, {"data": SESSIONS, "cursor": {}})
        elif path == "/api/session/active":
            self._send(
                200,
                {
                    "data": {
                        "ses_busy": {"type": "running"},
                        "ses_waiting": {"type": "running"},
                    }
                },
            )
        elif path in (
            "/api/session/ses_busy/form",
            "/api/session/ses_busy/permission",
            "/api/session/ses_waiting/permission",
        ):
            self._send(200, {"data": []})
        elif path == "/api/session/ses_waiting/form":
            self._send(
                200,
                {
                    "data": [
                        {
                            "id": "frm_1",
                            "title": "Questions",
                            "metadata": {"kind": "question"},
                            "fields": [{"key": "q0", "title": "Question"}],
                        }
                    ]
                },
            )
        elif path == "/api/session/ses_new/message":
            self._send(200, {"data": [{"id": "msg_1", "type": "assistant"}]})
        else:
            self._send(404, {"_tag": "NotFoundError"})

    def do_POST(self):
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if path == "/api/session":
            Handler.create_body = body
            self._send(200, {"data": {"id": "ses_new", "title": body.get("title")}})
        elif path == "/api/session/ses_new/prompt":
            Handler.prompt_body = body
            self._send(200, {"data": {"id": "msg_1", "type": "user"}})
        else:
            self._send(404, {"_tag": "NotFoundError"})


class OpenCodeV2ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.client = OpenCodeClient(
            f"http://127.0.0.1:{cls.server.server_port}", USER, PASSWORD
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_uses_api_info(self):
        self.assertEqual(self.client.health()["version"], "2.2.5")

    def test_sessions_unwrap_data(self):
        sessions = self.client.sessions()
        self.assertEqual([s["id"] for s in sessions], ["ses_busy", "ses_waiting", "ses_idle"])

    def test_statuses_distinguish_busy_waiting_and_idle(self):
        self.assertEqual(
            self.client.statuses(),
            {
                "ses_busy": {"type": "busy"},
                "ses_waiting": {"type": "waiting_for_user"},
                "ses_idle": {"type": "idle"},
            },
        )

    def test_create_session_sends_project_location_and_model(self):
        created = self.client.create_session(
            "test title",
            directory="/tmp/project",
            agent="build",
            model={"providerID": "deepseek", "id": "deepseek-flash", "variant": "max"},
        )
        self.assertEqual(created["id"], "ses_new")
        self.assertEqual(Handler.create_body["title"], "test title")
        self.assertEqual(Handler.create_body["location"], {"directory": "/tmp/project"})
        self.assertEqual(Handler.create_body["agent"], "build")
        self.assertEqual(
            Handler.create_body["model"],
            {"providerID": "deepseek", "id": "deepseek-flash", "variant": "max"},
        )

    def test_prompt_uses_v2_text_field(self):
        self.client.prompt_async("ses_new", "hello")
        self.assertEqual(Handler.prompt_body, {"text": "hello"})

    def test_messages_unwrap_data(self):
        self.assertEqual(self.client.session_messages("ses_new")[0]["id"], "msg_1")


if __name__ == "__main__":
    unittest.main()
