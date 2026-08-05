# Installation Guide

## Prerequisites

- **Python 3.11+** — [download](https://python.org/downloads/)
- **uv** — fast Python package manager — [install](https://docs.astral.sh/uv/getting-started/installation/)
- **Internet access** — the default `edge-tts` engine synthesizes speech via Microsoft's online service. Without a network connection, use the offline `system` engine instead (see [Voice Profiles](voices.md)).

## Install from Source

```bash
git clone https://github.com/arvidsson-geins/agent-ptt.git
cd agent-ptt
uv sync
```

This installs all dependencies into a local `.venv` and makes the `agent-ptt` CLI available via `uv run`.

## Verify Installation

```bash
uv run agent-ptt --help
```

You should see the full command list: `server`, `channel`, `join`, `say`, `listen`, `voices`, `config`, `leave`.

## Running the Server

`agent-ptt server start` runs a **long-lived foreground process** — it stays attached to the terminal until you stop it with `Ctrl+C`. Every other command (`channel`, `join`, `say`, `listen`) talks to this server over HTTP, so it must be running first.

- **Interactive use:** start the server in one terminal, then run the other commands in a second terminal.
- **Scripted / agent use:** start it in the background so your script isn't blocked, e.g.:

```bash
uv run agent-ptt server start &   # background the server
# wait for it to come up, then use the CLI
until curl -sf http://localhost:8770/channels >/dev/null; do sleep 0.2; done
uv run agent-ptt channel create "War Room"
```

Once it's running, open **[http://localhost:8770](http://localhost:8770)** for the built-in web UI.

## System-Specific Notes

### macOS

Audio playback uses CoreAudio via `sounddevice` — works out-of-the-box on Apple Silicon and Intel Macs.

### Linux

You may need to install PortAudio:

```bash
# Debian/Ubuntu
sudo apt-get install libportaudio2

# Fedora
sudo dnf install portaudio
```

**Headless servers (no audio hardware):** `sounddevice` will log a warning and speaker playback is disabled automatically — the server keeps running, and spectators can still receive audio over the `/audio` WebSocket stream (or the web UI). Local speaker output simply won't happen.

### Windows

`sounddevice` uses the Windows Audio Session API (WASAPI) — no additional drivers needed.

## Updating

```bash
cd agent-ptt
git pull
uv sync
```
