# Agent PTT — Roadmap

Plans and proposals for future development.

## Core Insight

The OmniVoice engine is just a HuggingFace `PreTrainedModel` with two methods: `from_pretrained()` and `generate()`. No subprocess sidecars, no GPU pools, no orchestration needed. We call it directly.

## Documents

| Document | Status | Description |
|----------|--------|-------------|
| [Local TTS Engines](local-tts-engines.md) | ✅ Shipped (via PyPI dep, not vendoring) | Depend on the `omnivoice` package for local neural TTS |
| [Engine Integration](engine-integration.md) | ✅ Shipped | `OmniVoiceTTSBackend` in `agent_ptt/engines/`, device detection, `omnivoice` extra |
| [Voice Design](voice-design.md) | ✅ Shipped | Instruct profiles, archetypes, `voice design`/`preview`/`clone` CLI |
| [Auto Voice Designer](auto-voice-designer.md) | ✅ Shipped | Hash + LLM designers with pinning, `voice pinned`/`redesign` CLI |
| [Distributed Channels](distributed-channels.md) | 📋 Proposal | Supabase/global storage: agents push from anywhere, audio nodes play anywhere |

## Priority Order (next up)

The original voice roadmap (items 1–4 above) shipped in July 2026. Next:

1. **Distributed Channels, Phase 1** — headless hub (`--no-audio`) deployed centrally, Turso storage (~0.5 day)
2. **Distributed Channels, Phase 2** — Supabase Postgres backend + first Alembic migration (~1 day)
3. **Distributed Channels, Phase 3** — pub/sub message bus + `agent-ptt node` audio nodes (~2-3 days)
4. **Distributed Channels, Phase 4** — auth for the public internet (~1 day)

## Current State

Agent PTT ships with three TTS backends:

| Engine | Type | Quality | Offline |
|--------|------|---------|---------|
| `edge-tts` | Cloud (Microsoft Edge) | ★★★★ | ❌ |
| `system` | OS voices (pyttsx3) | ★★ | ✅ |
| `omnivoice` | Local neural model (optional extra) | ★★★★★ | ✅ |

Plus: auto-designed pinned voices per handle (hash or local LLM), voice cloning, a `plugins/` directory with Claude Code + Codex announcers and the `/say` skill, and CI that releases the plugins on version tags.

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
