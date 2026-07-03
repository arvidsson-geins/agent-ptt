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
ANNOUNCE_PY = REPO_ROOT / "plugins" / "announcer" / "hooks" / "announce.py"

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


# ---------------------------------------------------------------------------
# Codex integration
# ---------------------------------------------------------------------------

CODEX_ANNOUNCE = REPO_ROOT / "plugins" / "codex-announcer" / "announce.py"
CODEX_INSTALL = REPO_ROOT / "plugins" / "codex-announcer" / "install.sh"


def test_codex_script_is_identical_to_claude_script():
    """One script serves both tools — fix bugs in one place and copy."""
    assert CODEX_ANNOUNCE.read_bytes() == ANNOUNCE_PY.read_bytes()


def test_agent_name_prefixes_the_handle(monkeypatch):
    calls = []
    monkeypatch.setattr(announce, "announce", lambda *a: calls.append(a))
    monkeypatch.setattr(announce, "AGENT_NAME", "Codex")
    monkeypatch.setenv("AGENT_PTT_FORK", "0")
    monkeypatch.setattr(
        announce.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "prompt": "ship it",
                    "cwd": "/tmp/my-project",
                    "session_id": "s1",
                }
            )
        ),
    )
    announce.main()
    assert calls == [("s1", "Codex · my-project", "Starting: ship it")]


def test_install_sh_writes_hooks_json(tmp_path):
    proc = subprocess.run(
        ["bash", str(CODEX_INSTALL)],
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert proc.returncode == 0, proc.stderr
    hooks_file = tmp_path / ".codex" / "hooks.json"
    config = json.loads(hooks_file.read_text())
    command = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "AGENT_PTT_AGENT=Codex" in command
    assert str(CODEX_ANNOUNCE) in command
    assert "__AGENT_PTT_PLUGIN_DIR__" not in command
    assert "Stop" in config["hooks"]


def test_install_sh_refuses_to_overwrite(tmp_path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "hooks.json").write_text('{"hooks": {}}')
    proc = subprocess.run(
        ["bash", str(CODEX_INSTALL)],
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    assert proc.returncode == 1
    assert json.loads((tmp_path / ".codex" / "hooks.json").read_text()) == {"hooks": {}}
    assert "AGENT_PTT_AGENT=Codex" in proc.stdout  # snippet printed for manual merge


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
