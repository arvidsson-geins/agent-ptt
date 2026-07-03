#!/usr/bin/env python3
"""Agent PTT announcer hook for Claude Code and Codex CLI.

Both tools send the same hook JSON on stdin, so one script serves both.
Announces in an Agent PTT voice channel what the current agent is doing:
- UserPromptSubmit -> "Starting: <short summary of the prompt>"
- Stop            -> "Done."

Each project joins as "Claude · <folder>" without picking a voice, so the
auto-voice-designer pins a distinct voice per project.

Design rules: this hook must NEVER interfere with coding. Every failure
path (server down, bad response, anything) exits 0 silently. After
parsing the event it forks and lets the parent exit immediately, so even
hosts without async hook support are never blocked. Stdlib only.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("AGENT_PTT_URL", "http://localhost:8770").rstrip("/")
CHANNEL_NAME = os.environ.get("AGENT_PTT_CHANNEL", "Claude Code")
AGENT_NAME = os.environ.get("AGENT_PTT_AGENT", "Claude")  # e.g. "Codex"
STATE_FILE = Path.home() / ".agent-ptt" / "announcer-state.json"
HTTP_TIMEOUT = float(os.environ.get("AGENT_PTT_TIMEOUT", "45"))
MAX_ANNOUNCE_CHARS = 140


def _request(method: str, path: str, payload: dict | None = None, timeout: float | None = None):
    """Minimal JSON HTTP helper. Raises on any failure."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout or HTTP_TIMEOUT) as resp:
        return json.loads(resp.read())


def summarize_prompt(prompt: str, limit: int = MAX_ANNOUNCE_CHARS) -> str:
    """First meaningful line of the prompt, cleaned and truncated for speech."""
    line = next((ln.strip() for ln in prompt.splitlines() if ln.strip()), "")
    line = " ".join(line.split())
    if len(line) > limit:
        cut = line[:limit]
        # Don't cut mid-word
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        line = cut + "…"
    return line


def _load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass  # cache is best-effort


def _find_or_create_channel() -> str:
    # The channel list is small; a quick probe also confirms the server is up
    channels = _request("GET", "/channels", timeout=1.5)
    for channel in channels:
        if channel.get("name") == CHANNEL_NAME:
            return channel["channel_id"]
    created = _request("POST", "/channels", {"name": CHANNEL_NAME})
    return created["channel_id"]


def _join(channel_id: str, handle: str) -> str:
    # No voice_id -> the server designs and pins a voice for this handle
    joined = _request("POST", f"/channels/{channel_id}/join", {"handle": handle})
    return joined["key_id"]


def announce(session_id: str, handle: str, text: str) -> None:
    channel_id = _find_or_create_channel()

    state = _load_state()
    cache_key = f"{session_id}:{handle}"
    cached = state.get(cache_key, {})
    key_id = cached.get("key_id") if cached.get("channel_id") == channel_id else None

    if key_id is None:
        key_id = _join(channel_id, handle)
        state[cache_key] = {"channel_id": channel_id, "key_id": key_id}
        _save_state(state)

    try:
        _request("POST", f"/channels/{channel_id}/say", {"key_id": key_id, "text": text})
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        # Stale key (server restarted between calls) — rejoin once
        key_id = _join(channel_id, handle)
        state[cache_key] = {"channel_id": channel_id, "key_id": key_id}
        _save_state(state)
        _request("POST", f"/channels/{channel_id}/say", {"key_id": key_id, "text": text})


def _detach() -> None:
    """Fork so the hook host gets its exit code immediately (POSIX only).

    The child carries on with the network work. Disable with
    AGENT_PTT_FORK=0 (used by tests).
    """
    if os.environ.get("AGENT_PTT_FORK", "1") == "0" or not hasattr(os, "fork"):
        return
    if os.fork() != 0:
        os._exit(0)  # parent: hook is done as far as the host knows


def main() -> None:
    if os.environ.get("AGENT_PTT_ANNOUNCE", "1") == "0":
        return

    event = json.load(sys.stdin)
    event_name = event.get("hook_event_name", "")

    if event_name == "UserPromptSubmit":
        summary = summarize_prompt(event.get("prompt", ""))
        if not summary:
            return
        text = f"Starting: {summary}"
    elif event_name == "Stop":
        if event.get("stop_hook_active"):
            return
        text = "Done."
    else:
        return

    project = Path(event.get("cwd") or ".").name or "somewhere"
    handle = f"{AGENT_NAME} · {project}"

    _detach()
    announce(event.get("session_id", "unknown"), handle, text)


if __name__ == "__main__":
    # Never break the coding session — announcements are best-effort
    with contextlib.suppress(Exception):
        main()
    sys.exit(0)
