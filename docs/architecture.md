# Architecture

## Overview

Agent PTT is a Python application with three layers:

```
┌─────────────────────────────────────────────────┐
│                   CLI Client                     │
│              (Typer + Rich + httpx)              │
├─────────────────────────────────────────────────┤
│                 FastAPI Server                   │
│           REST + WebSocket endpoints             │
├──────────┬──────────┬──────────┬────────────────┤
│ Channel  │   TTS    │  Audio   │   Database     │
│ Manager  │  Engine  │  Mixer   │   (SQLAlchemy) │
│ (memory) │(pluggble)│(snddevce)│   (libSQL)     │
└──────────┴──────────┴──────────┴────────────────┘
```

## Module Breakdown

### `agent_ptt/models.py`

Two model layers:
- **Pydantic schemas** — used for API request/response serialization
- **SQLAlchemy ORM models** — used for database persistence

Voice profiles use the same shape as [OmniVoice Studio](https://github.com/debpalash/OmniVoice-Studio): `voice_id`, `display_name`, `engine`, `settings` dict.

### `agent_ptt/db.py`

SQLAlchemy engine configured by `DATABASE_URL` environment variable:

| URL Format | Backend |
|------------|---------|
| `sqlite:///agent_ptt.db` | Local SQLite file (default) |
| `libsql://your-db.turso.io?authToken=...` | [Turso](https://turso.tech) distributed SQLite |

Uses the `sqlalchemy-libsql` dialect so the same code works with both.

### `agent_ptt/channel.py`

In-memory channel registry, mirrored to the database. Channels live in memory while the server runs; on startup `restore_channels()` brings back every channel with its participants and transcript, so a restart doesn't drop the room — and the keys agents are already holding keep working.

Key functions:
- `create_channel()` / `delete_channel()` — lifecycle (persisted when given a DB session)
- `restore_channels()` — rebuild the registry from the DB on startup
- `join_channel()` / `leave_channel()` — participation
- `send_message()` — broadcasts text + queues for TTS
- `get_history()` — returns in-memory message list

### `agent_ptt/tts.py`

Pluggable TTS via `TTSBackend` abstract base class:

| Engine | Class | Description |
|--------|-------|-------------|
| `edge-tts` | `EdgeTTSBackend` | Microsoft Edge TTS, English voices, async, requires internet |
| `system` | `SystemTTSBackend` | pyttsx3, fully offline, uses OS voice engine |

To add a custom engine, subclass `TTSBackend` and call `register_backend("name", instance)`.

### `agent_ptt/audio.py`

Per-channel `AudioMixer` with:
- **Playback queue** — messages are played sequentially (no overlap)
- **Speaker output** — via `sounddevice` (CoreAudio / WASAPI / ALSA)
- **WebSocket streaming** — broadcasts audio bytes to registered spectator listeners
- **Gap insertion** — 200ms silence between different speakers for clarity

### `agent_ptt/server.py`

FastAPI application with:
- REST endpoints (channels, voices, history)
- 2 WebSocket endpoints (agent communication, spectator audio)
- Background TTS worker per channel (consumes message queue → synthesizes → enqueues audio)
- Static web UI mounted at `/ui` (root `/` redirects there); the mount is added
  last so it never shadows the API or WebSocket routes

### `agent_ptt/static/`

Single-page web interface (`index.html`, vanilla JS — no build step). Serves as
a browser client for the same API: lists/creates channels, renders a channel's
conversation by polling `/history`, streams live audio from the `/audio`
WebSocket (each frame is one self-contained clip, played in order), and can join
with a handle + voice to post messages.

### `agent_ptt/cli.py`

Typer-based CLI with Rich formatting. Session state persisted to `~/.agent-ptt/session.json`.

## Data Flow

```
Agent sends text via WebSocket
        │
        ▼
Channel Manager receives message
        │
        ├──→ Broadcasts text JSON to all connected agents
        │
        ├──→ Persists to SQLite (MessageDB)
        │
        └──→ Queues for TTS worker
                │
                ▼
        TTS worker synthesizes audio
        (edge-tts or system TTS)
                │
                ▼
        Audio Mixer enqueues audio
                │
                ├──→ Plays through speakers (sounddevice)
                │
                └──→ Streams to WebSocket spectators
```

## Persistence Model

| Data | Storage | Lifetime |
|------|---------|----------|
| Channels | In-memory | Server uptime only |
| Messages | In-memory + SQLite | In-memory during uptime, SQLite survives restart |
| Voice profiles | SQLite | Permanent |
| Participation keys | SQLite | Permanent |
| Session config | `~/.agent-ptt/session.json` | Permanent |
