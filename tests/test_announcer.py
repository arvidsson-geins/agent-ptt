"""The Claude Code announcer hook (claude-plugin/hooks/announce.py).

The script is stdlib-only; we import it directly for unit tests and run
it as a subprocess for the never-break-coding guarantee.
"""

import importlib.util
import io
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
ANNOUNCE_PY = REPO_ROOT / "claude-plugin" / "hooks" / "announce.py"

spec = importlib.util.spec_from_file_location("announce", ANNOUNCE_PY)
announce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(announce)


# ---------------------------------------------------------------------------
# summarize_prompt
# ---------------------------------------------------------------------------


def test_summarize_takes_first_meaningful_line():
    prompt = "\n\n  fix the login bug  \nand also update the docs"
    assert announce.summarize_prompt(prompt) == "fix the login bug"


def test_summarize_collapses_whitespace():
    assert announce.summarize_prompt("add   tests\tfor the   parser") == "add tests for the parser"


def test_summarize_truncates_long_prompts_at_word_boundary():
    prompt = "please refactor " + "the entire authentication and session layer " * 10
    result = announce.summarize_prompt(prompt)
    assert len(result) <= announce.MAX_ANNOUNCE_CHARS + 1
    assert result.endswith("…")
    assert not result[:-1].endswith(" ")


def test_summarize_empty_prompt():
    assert announce.summarize_prompt("") == ""
    assert announce.summarize_prompt("\n\n  \n") == ""


# ---------------------------------------------------------------------------
# State cache
# ---------------------------------------------------------------------------


def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(announce, "STATE_FILE", tmp_path / "state.json")
    announce._save_state({"session:handle": {"channel_id": "c1", "key_id": "k1"}})
    assert announce._load_state() == {"session:handle": {"channel_id": "c1", "key_id": "k1"}}


def test_state_missing_or_corrupt_is_empty(tmp_path, monkeypatch):
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(announce, "STATE_FILE", state_file)
    assert announce._load_state() == {}
    state_file.write_text("{not json")
    assert announce._load_state() == {}


# ---------------------------------------------------------------------------
# Never break coding: subprocess exits 0 fast when the server is down
# ---------------------------------------------------------------------------


def _run_hook(event: dict, url: str) -> tuple[subprocess.CompletedProcess, float]:
    start = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(ANNOUNCE_PY)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "AGENT_PTT_URL": url, "HOME": "/tmp"},
    )
    return proc, time.monotonic() - start


def test_exits_zero_and_silent_when_server_down():
    event = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "do something",
        "cwd": "/tmp/my-project",
        "session_id": "s1",
    }
    proc, elapsed = _run_hook(event, "http://localhost:19999")
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert elapsed < 6, f"hook took {elapsed:.1f}s with server down"


def test_exits_zero_on_garbage_stdin():
    proc = subprocess.run(
        [sys.executable, str(ANNOUNCE_PY)],
        input="this is not json",
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_disabled_via_env_exits_immediately():
    proc = subprocess.run(
        [sys.executable, str(ANNOUNCE_PY)],
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "x"}),
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "AGENT_PTT_ANNOUNCE": "0"},
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_stop_hook_active_is_skipped(monkeypatch):
    """When stop_hook_active is set, no announcement is attempted."""
    calls = []
    monkeypatch.setattr(announce, "announce", lambda *a: calls.append(a))
    monkeypatch.setattr(
        announce.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "Stop", "stop_hook_active": True})),
    )
    announce.main()
    assert calls == []


def test_ignores_unknown_events(monkeypatch):
    calls = []
    monkeypatch.setattr(announce, "announce", lambda *a: calls.append(a))
    monkeypatch.setattr(
        announce.sys,
        "stdin",
        io.StringIO(json.dumps({"hook_event_name": "PreToolUse"})),
    )
    announce.main()
    assert calls == []
