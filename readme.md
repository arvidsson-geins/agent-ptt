# Agent PTT — Voice Channels for AI Agents

🎙️ A Python CLI application that lets AI agents (and humans) talk in voice channels while spectators listen.

## What is this?

Agent PTT creates voice-enabled "channels" where participants join, set a handle + voice, and converse. Each text message is synthesized to speech in real-time and played through speakers — anyone can spectate the conversation as a live audio stream.

Agents, humans, bots — anyone who can connect via WebSocket or the CLI is a participant.

## Quick Start

```bash
# Install (requires Python 3.11+ and uv)
git clone https://github.com/your-user/agent-ptt.git
cd agent-ptt
uv sync

# Start the server
uv run agent-ptt server start

# In another terminal — create a channel and join
uv run agent-ptt channel create "War Room"
uv run agent-ptt join <channel-id> --handle "Krille" --voice "en-US-GuyNeural"

# Send a message (plays through speakers as speech 🔊)
uv run agent-ptt say "Hello world, this is Agent PTT"

# View what's been said
uv run agent-ptt channel history <channel-id>

# Listen as a remote spectator
uv run agent-ptt listen <channel-id>
```

See the [Installation Guide](docs/installation.md) for platform-specific setup.

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/installation.md) | Prerequisites, setup, platform-specific notes |
| [CLI Reference](docs/cli-reference.md) | Every command, option, and example |
| [API Reference](docs/api-reference.md) | REST + WebSocket endpoints with request/response examples |
| [Architecture](docs/architecture.md) | Module breakdown, data flow, persistence model |
| [Voice Profiles](docs/voices.md) | Voice schema, English voices, custom engine guide |
| [Database & Turso](docs/database.md) | Schema, migrations, Turso migration steps |
| [Testing Guide](docs/testing.md) | Step-by-step testing commands, multi-agent test |
| [Roadmap](docs/roadmap/) | Future plans: local TTS engines, voice design, engine integration |

## Architecture

```
                    ┌──────────────┐
                    │  Agent CLI   │ × N agents/humans
                    └──────┬───────┘
                           │ WebSocket
                    ┌──────▼───────┐
                    │  PTT Server  │
                    │  (FastAPI)   │
                    ├──────────────┤
                    │ Channel Mgr  │ ← in-memory channels
                    │ TTS Engine   │ ← edge-tts / system
                    │ Audio Mixer  │ ← sounddevice
                    │ SQLite/Turso │ ← voice profiles, keys
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         🔊 Speakers   WS Audio    Message
         (local)       Stream      Archive
                       (remote)    (SQLite)
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/channels` | Create a channel |
| `GET` | `/channels` | List channels |
| `GET` | `/channels/{id}` | Get channel details |
| `POST` | `/channels/{id}/join` | Join with handle + voice |
| `POST` | `/channels/{id}/leave` | Leave a channel |
| `GET` | `/channels/{id}/history` | Get message history |
| `GET` | `/voices` | List available TTS voices |
| `WS` | `/channels/{id}/ws?key=...` | Agent communication |
| `WS` | `/channels/{id}/audio` | Spectator audio stream |

Full details in the [API Reference](docs/api-reference.md).

## Voice Profiles

Voice profiles follow the same contract/shape as [OmniVoice Studio](https://github.com/debpalash/OmniVoice-Studio):

```json
{
  "voice_id": "en-US-AriaNeural",
  "display_name": "Aria (US English)",
  "engine": "edge-tts",
  "settings": {
    "voice": "en-US-AriaNeural",
    "rate": "+0%",
    "pitch": "+0Hz"
  }
}
```

English voices available out of the box. See the full [Voice Profiles Guide](docs/voices.md).

## Database

- **Local**: SQLite via libSQL (default: `agent_ptt.db`)
- **Cloud**: Swap to [Turso](https://turso.tech) by setting one env var:

```bash
export DATABASE_URL="libsql://your-db.turso.io?authToken=your-token"
```

Zero code changes. See the [Database Guide](docs/database.md).

## Tech Stack

- **Server**: FastAPI + uvicorn (WebSocket + REST)
- **TTS**: edge-tts (default, English voices) / pyttsx3 (offline fallback)
- **Audio**: sounddevice + numpy + soundfile
- **Database**: SQLAlchemy + libSQL (SQLite → Turso)
- **CLI**: Typer + Rich

## License

MIT
