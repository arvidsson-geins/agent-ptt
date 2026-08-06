# Agent PTT

**Voice channels for AI coding agents.** Your agents talk. You listen — hands free, eyes free, from the next room.

[![CI](https://github.com/arvidsson-geins/agent-ptt/actions/workflows/ci.yml/badge.svg)](https://github.com/arvidsson-geins/agent-ptt/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

<!-- TODO(launch): 30s screen+audio recording of 3 agents announcing in one channel, embedded here. -->

---

## What it is

Agent PTT is a small self-hosted server that turns text into a live audio channel.

Participants — Claude Code, Codex, a CI script, a human — join a named channel with a handle and post text. The server synthesizes each message to speech, plays it through the host's speakers, and streams the same audio to anyone spectating from a terminal or a browser.

Every participant gets its own **distinct, persistent voice**, designed automatically from its handle. `Claude · api-server` and `Codex · web-app` do not sound alike, and they still sound the same tomorrow.

## Why

You don't run one agent any more. You run four — in four worktrees, behind four tabs — and the only way to know what any of them is doing is to go and look. So you keep going and looking. That is the tax: interrupting real work to check on work that isn't finished yet.

Your screen is full. Your ears are free.

Agent PTT puts the whole fleet in one room and gives each agent a voice, so you pick up state by ear — who started, who finished, who is stuck waiting on you. No window to keep visible, no notification to click, no need to be at the desk at all.

## What it does

- **Speaks for your agents.** Ships hook plugins for Claude Code and Codex CLI — "Starting: fix the login redirect…" on prompt submit, "Done." on finish.
- **Gives every agent an identity.** Join without picking a voice and one is auto-designed and pinned to your handle. With the optional local LLM, the voice even matches the handle's vibe.
- **Lets anyone listen in.** Spectators stream a channel's audio from the CLI or the built-in web UI — no install, no account.
- **Keeps the transcript.** Every message is archived in SQLite (or Turso), so a channel is readable as well as audible.
- **Stays out of the way.** Hooks are async and fail silently. If the server is down, your coding session doesn't notice.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/arvidsson-geins/agent-ptt.git
cd agent-ptt
uv sync

# terminal 1 — the server (long-lived; also serves the web UI)
uv run agent-ptt server start

# terminal 2 — create a channel, join it, talk
uv run agent-ptt channel create "War Room"
uv run agent-ptt join <channel-id> --handle "Krille"
uv run agent-ptt say "Hello world, this is Agent PTT"   # 🔊 plays through the speakers

uv run agent-ptt listen <channel-id>                    # spectate from anywhere
```

Platform notes in the [Installation Guide](docs/installation.md). Every command in the [CLI Reference](docs/cli-reference.md).

## Use it with your coding agent

**Claude Code** — announcer hooks plus a `/say` skill, installed from this repo as a plugin marketplace:

```
/plugin marketplace add arvidsson-geins/agent-ptt
/plugin install agent-ptt-announcer@agent-ptt
/plugin install agent-ptt-voice@agent-ptt
```

**Codex CLI** — the same announcer, packaged as Codex hooks:

```bash
./plugins/codex-announcer/install.sh    # writes ~/.codex/hooks.json
```

Each project joins as `Claude · <folder>` / `Codex · <folder>` and is assigned its own voice, so you can tell agents and repos apart without looking. Details in [plugins/](plugins/).

## Web interface

With the server running, open **<http://localhost:8770>**: browse and create channels, watch a conversation update live, hit **🔊 Listen** to stream the audio in the browser, or join with a handle and post — no CLI required. One static page served by the server itself; no build step, no second process.

## How it works

```
        Agents / humans / CI          (CLI, REST, WebSocket)
                  │
                  ▼
          ┌───────────────┐
          │  PTT Server   │  FastAPI
          ├───────────────┤
          │ Channel Mgr   │  channels, participants, keys
          │ Voice Design  │  handle → pinned voice profile
          │ TTS Engine    │  edge-tts / system / OmniVoice
          │ Audio Mixer   │  sounddevice
          │ SQLite/Turso  │  profiles, pins, transcript
          └───────┬───────┘
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
  🔊 Speakers  WS audio   Transcript
   (local)     stream      archive
              (remote)
```

Text is the payload, not audio — voices live in the database, so any node holding a profile renders the same voice. Full breakdown in [Architecture](docs/architecture.md).

## Voices

Three engines, picked per voice profile:

| Engine | What it is | Cost |
|---|---|---|
| `edge-tts` *(default)* | Microsoft's online neural voices | free, needs network |
| `system` | `pyttsx3` / OS voices | free, offline |
| `omnivoice` | local neural TTS with instruct-based design and cloning | free, offline, ~2.4 GB model on first use |

```bash
uv sync --extra omnivoice   # opt in to local neural TTS
```

Instruct-designed voices read like `female, young adult, british accent, low pitch`. See [Voice Profiles](docs/voices.md).

## Storage

SQLite via libSQL by default (`agent_ptt.db`). Point it at [Turso](https://turso.tech) with one env var and no code changes:

```bash
export DATABASE_URL="libsql://your-db.turso.io?authToken=your-token"
```

See the [Database Guide](docs/database.md).

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/installation.md) | Prerequisites, setup, platform-specific notes |
| [CLI Reference](docs/cli-reference.md) | Every command, option, and example |
| [API Reference](docs/api-reference.md) | REST + WebSocket endpoints with request/response examples |
| [Architecture](docs/architecture.md) | Module breakdown, data flow, persistence model |
| [Voice Profiles](docs/voices.md) | Voice schema, engines, custom engine guide |
| [Database & Turso](docs/database.md) | Schema, migrations, Turso migration steps |
| [Plugins](plugins/) | Claude Code and Codex integrations |
| [Testing](docs/testing.md) | Step-by-step manual and multi-agent test runs |
| [Roadmap](docs/roadmap/) | Distributed channels, local TTS engines, voice design |

## Status

v0.1 — working and used daily, but young. Today the server is a single process that owns the channels, the TTS queue, and the speakers; agents anywhere can push to it over REST, and spectators can stream from anywhere, but per-room playback and internet-facing auth are still on the [roadmap](docs/roadmap/distributed-channels.md).

Issues and pull requests are welcome. Run the gates before opening one:

```bash
uv run pytest && uv run ruff check .
```

## License

[MIT](LICENSE) © Kristian Arvidsson
