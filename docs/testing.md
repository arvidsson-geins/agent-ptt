# Agent PTT — Testing Guide

## Automated Tests

```bash
uv sync                                  # installs dev dependencies (pytest, ruff)
uv run pytest                            # run the full suite
uv run pytest tests/test_api.py -k name  # run a single file or test
uv run ruff check .                      # lint
uv run ruff format .                     # format
```

The suite in `tests/` covers the channel manager, data models, TTS registry, audio mixer bookkeeping, and all REST + WebSocket endpoints. TTS synthesis and speaker playback are faked (`tests/conftest.py`), and a temporary SQLite database is used — no network, audio hardware, or running server required.

What automated tests **cannot** cover is the audible path: real edge-tts synthesis and actual speaker output. Use the manual walkthrough below for that.

## Manual Testing

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) installed

### Setup

```bash
cd ~/Documents/Dev/projects/agent-ptt
uv sync
```

## Start the Server

```bash
uv run agent-ptt server start --port 8770
```

Leave this running in its own terminal.

## Test Commands (in a new terminal)

```bash
cd ~/Documents/Dev/projects/agent-ptt

# Create a channel
uv run agent-ptt channel create "Test Room"

# List channels (grab the channel ID from here)
uv run agent-ptt channel list

# Join a channel (replace <channel-id> with the actual ID)
uv run agent-ptt join <channel-id> --handle "Krille" --voice "en-US-GuyNeural"

# Send a message — plays through speakers as speech 🔊
uv run agent-ptt say "Hello world, this is Agent PTT"

# List available voices
uv run agent-ptt voices

# Listen as a spectator (in yet another terminal)
uv run agent-ptt listen <channel-id>

# Leave the channel
uv run agent-ptt leave

# Check your current config/session
uv run agent-ptt config
```

## Multi-Agent Test

Open 3 terminals:

**Terminal 1 — Server:**
```bash
cd ~/Documents/Dev/projects/agent-ptt
uv run agent-ptt server start --port 8770
```

**Terminal 2 — Agent 1:**
```bash
cd ~/Documents/Dev/projects/agent-ptt
uv run agent-ptt channel create "War Room"
# copy the channel ID
uv run agent-ptt join <channel-id> --handle "Claude" --voice "en-US-AriaNeural"
uv run agent-ptt say "Hello, I'm Claude. Ready to discuss."
```

**Terminal 3 — Agent 2:**
```bash
cd ~/Documents/Dev/projects/agent-ptt
uv run agent-ptt join <channel-id> --handle "GPT" --voice "en-US-GuyNeural"
uv run agent-ptt say "Hey Claude, GPT here. Let's go."
```

Both messages will be synthesized with different voices and played through speakers.

## Popular Voices

| Voice ID | Description |
|----------|-------------|
| `en-US-AriaNeural` | US English, female (default) |
| `en-US-GuyNeural` | US English, male |
| `en-US-JennyNeural` | US English, female |
| `en-US-DavisNeural` | US English, male |
| `en-GB-SoniaNeural` | British English, female |
| `en-GB-RyanNeural` | British English, male |
| `en-AU-NatashaNeural` | Australian English, female |
| `en-AU-WilliamNeural` | Australian English, male |

Run `uv run agent-ptt voices` for the full list of English voices.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///agent_ptt.db` | Database connection (swap to Turso: `libsql://...`) |
