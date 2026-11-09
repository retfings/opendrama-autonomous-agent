import tempfile
from pathlib import Path
from opendrama_agent.state import load, save

def test_state_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "state.json"
        value = load(p)
        value["session_id"] = "ses_test"
        save(p, value)
        assert load(p)["session_id"] == "ses_test"
