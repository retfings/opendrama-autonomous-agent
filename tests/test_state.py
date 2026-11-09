import tempfile
import unittest
from pathlib import Path

from opendrama_agent.state import load, save


class StateTest(unittest.TestCase):
    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            value = load(p)
            value["session_id"] = "ses_test"
            save(p, value)
            self.assertEqual(load(p)["session_id"], "ses_test")


if __name__ == "__main__":
    unittest.main()
