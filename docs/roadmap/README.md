# Agent PTT — Roadmap

Plans and proposals for future development.

## Core Insight

The OmniVoice engine is just a HuggingFace `PreTrainedModel` with two methods: `from_pretrained()` and `generate()`. No subprocess sidecars, no GPU pools, no orchestration needed. We call it directly.

## Documents

| Document | Status | Description |
|----------|--------|-------------|
| [Local TTS Engines](local-tts-engines.md) | 📋 Proposal | Vendor or depend on the `omnivoice` package for local neural TTS |
| [Engine Integration](engine-integration.md) | 📋 Proposal | `OmniVoiceTTSBackend` implementation, device detection, optional deps |
| [Voice Design](voice-design.md) | 📋 Proposal | Instruct tags, archetype gallery, voice designer CLI, voice cloning |
| [Auto Voice Designer](auto-voice-designer.md) | 📋 Proposal | LLM auto-generates unique voices per handle, pins to DB |

## Priority Order

1. **Engine Integration** — add `OmniVoiceTTSBackend` (~1-2 days)
2. **Auto Voice Designer** — hash-based auto-assignment (~1 day), then LLM upgrade (~1-2 days)
3. **Voice Design** — instruct-based archetypes + voice designer CLI (~1-2 days)
4. **Voice Cloning** — reference audio cloning (~1 day, optional)

## Current State

Agent PTT ships with two TTS backends today:

| Engine | Type | Quality | Offline |
|--------|------|---------|---------|
| `edge-tts` | Cloud (Microsoft Edge) | ★★★★ | ❌ |
| `system` | OS voices (pyttsx3) | ★★ | ✅ |

The roadmap adds:

| Engine | Type | Quality | Offline |
|--------|------|---------|---------|
| `omnivoice` | Local neural model | ★★★★★ | ✅ |

## Install Strategy

The OmniVoice engine and voice designer are **optional extras** to keep the base install light:

```bash
# Base install (edge-tts only, ~200 MB)
uv sync

# With local OmniVoice engine (~2.4 GB model download on first use)
uv sync --extra omnivoice

# With LLM-powered voice designer (~500 MB model)
uv sync --extra voice-designer

# Everything
uv sync --extra omnivoice --extra voice-designer
```
