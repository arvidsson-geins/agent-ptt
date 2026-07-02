# Installation Guide

## Prerequisites

- **Python 3.11+** — [download](https://python.org/downloads/)
- **uv** — fast Python package manager — [install](https://docs.astral.sh/uv/getting-started/installation/)

## Install from Source

```bash
git clone https://github.com/your-user/agent-ptt.git
cd agent-ptt
uv sync
```

This installs all dependencies into a local `.venv` and makes the `agent-ptt` CLI available via `uv run`.

## Verify Installation

```bash
uv run agent-ptt --help
```

You should see the full command list: `server`, `channel`, `join`, `say`, `listen`, `voices`, `config`, `leave`.

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

### Windows

`sounddevice` uses the Windows Audio Session API (WASAPI) — no additional drivers needed.

## Updating

```bash
cd agent-ptt
git pull
uv sync
```
