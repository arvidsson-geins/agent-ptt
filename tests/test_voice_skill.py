"""The /say skill script (plugins/voice/scripts/say.py)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SAY_PY = REPO_ROOT / "plugins" / "voice" / "scripts" / "say.py"

spec = importlib.util.spec_from_file_location("say", SAY_PY)
say = importlib.util.module_from_spec(spec)
spec.loader.exec_module(say)


def test_clean_message_collapses_whitespace():
    assert say.clean_message("deploy\n  finished,\tall good") == "deploy finished, all good"


def test_clean_message_truncates_at_word_boundary():
    message = "status update " * 60
    result = say.clean_message(message)
    assert len(result) <= say.MAX_SAY_CHARS + 1
    assert result.endswith("…")


def test_clean_message_empty():
    assert say.clean_message("") == ""
    assert say.clean_message("   \n ") == ""


def _run_say(args: list[str], url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SAY_PY), *args],
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "AGENT_PTT_URL": url, "HOME": "/tmp"},
    )


def test_fails_loud_when_server_down():
    """Explicitly invoked — must report the failure, not swallow it."""
    proc = _run_say(["announce the deploy"], "http://localhost:19999")
    assert proc.returncode == 1
    assert "agent-ptt say failed" in proc.stderr
    assert "uv run agent-ptt server start" in proc.stderr


def test_usage_error_without_message():
    proc = _run_say([], "http://localhost:19999")
    assert proc.returncode == 1
    assert "usage" in proc.stderr


def test_say_reuses_cached_key(monkeypatch, tmp_path):
    """Second call must not join again — the cached key is reused."""
    monkeypatch.setattr(say, "STATE_FILE", tmp_path / "state.json")
    requests = []

    def fake_request(method, path, payload=None, timeout=None):
        requests.append((method, path))
        if path == "/channels":
            return [{"name": say.CHANNEL_NAME, "channel_id": "chan-1"}]
        if path.endswith("/join"):
            return {"key_id": "key-1"}
        if path.endswith("/say"):
            return {"message_id": "m1"}
        raise AssertionError(f"unexpected request {method} {path}")

    monkeypatch.setattr(say, "_request", fake_request)

    say.say("first")
    say.say("second")

    joins = [r for r in requests if r[1].endswith("/join")]
    says = [r for r in requests if r[1].endswith("/say")]
    assert len(joins) == 1
    assert len(says) == 2
    cached = json.loads((tmp_path / "state.json").read_text())
    assert next(iter(cached.values())) == {"channel_id": "chan-1", "key_id": "key-1"}
