# Voice Profiles

## Overview

Voice profiles define how an agent's text messages sound when synthesized to speech. They follow the same contract/shape as [OmniVoice Studio](https://github.com/debpalash/OmniVoice-Studio), making configs portable between the two apps.

## Schema

```json
{
  "voice_id": "en-US-AriaNeural",
  "display_name": "Aria (US English)",
  "engine": "edge-tts",
  "settings": {
    "voice": "en-US-AriaNeural",
    "rate": "+0%",
    "pitch": "+0Hz"
  },
  "created_at": "2026-07-02T07:19:57.000Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `voice_id` | string | Unique identifier (maps to engine-specific voice name) |
| `display_name` | string | Human-readable name |
| `engine` | string | TTS engine identifier (`edge-tts`, `system`, `omnivoice`) |
| `settings` | object | Engine-specific parameters |
| `created_at` | datetime | When the profile was created |

## Stored Profiles & Auto-Designed Voices

Profiles can be persisted in the database and referenced by `voice_id` when joining. Manage them with the `voice` CLI group (`agent-ptt voice list|show|save|delete`) or the `/voices/profiles` REST endpoints.

Joining **without** `--voice` auto-designs a deterministic voice from your handle and pins it in the `pinned_voices` table — the same handle always gets the same voice across sessions:

```bash
agent-ptt join <channel-id> --handle "Claude"
# ✅ Joined as [Claude]
#    Voice: auto-designed {"voice": "en-GB-RyanNeural", "rate": "+5%", "pitch": "-8Hz"}
```

On the base install the design picks an edge-tts voice with rate/pitch variation; with the `omnivoice` extra installed it generates an instruct string instead.

When the **LLM voice designer** is installed (`uv sync --extra voice-designer`, already satisfied by the omnivoice extra), a small local LLM (Qwen2.5-0.5B, ~1 GB download on first use) picks instruct attributes matching the *vibe* of the handle instead of a hash. The LLM's answer is validated against the model vocabulary and any invalid or missing attribute falls back to the deterministic hash, so a bad answer can never produce a broken voice. `agent-ptt voice pinned` shows which source designed each voice; `agent-ptt voice redesign <handle>` rolls a new one.

## Engine-Specific Settings

### edge-tts

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `voice` | string | `en-US-AriaNeural` | Edge TTS voice short name |
| `rate` | string | `+0%` | Speed adjustment (`-50%` to `+100%`) |
| `pitch` | string | `+0Hz` | Pitch adjustment (`-50Hz` to `+50Hz`) |
| `locale` | string | — | Language/region code (read-only, from voice listing) |
| `gender` | string | — | `Male` or `Female` (read-only, from voice listing) |

### system (pyttsx3)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `voice` | string | — | System voice ID (platform-specific) |
| `rate` | integer | `200` | Words per minute |

### omnivoice (local neural TTS — requires `uv sync --extra omnivoice`)

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `instruct` | string | — | Voice design items, comma-separated, e.g. `female, young adult, british accent, low pitch` |
| `ref_audio` | string | — | Path to a 5–30s reference clip for voice cloning |
| `ref_text` | string | — | Transcript of the reference clip (required with `ref_audio`) |
| `language` | string | — | Language code, e.g. `en` |
| `speed` | number | `1.0` | Speaking speed multiplier |

The model (~2.4 GB, `k2-fsa/OmniVoice`) downloads from HuggingFace Hub on first synthesis into `~/.cache/huggingface` (relocate with `HF_HOME`). Six instruct-based archetypes ship built in: `narrator`, `podcaster`, `newscaster`, `storyteller`, `assistant`, `professor` — see them with `agent-ptt voices --engine omnivoice`.

Valid instruct items (the model rejects anything else): `male`/`female`; `child`/`teenager`/`young adult`/`middle-aged`/`elderly`; `american`/`australian`/`british`/`canadian`/`chinese`/`indian`/`japanese`/`korean`/`portuguese`/`russian` + ` accent`; `very low`/`low`/`moderate`/`high`/`very high` + ` pitch`; `whisper`. Note this differs from the `[tag:value]` format sketched in the roadmap docs.

## Available Voices

| Voice ID | Gender | Accent |
|----------|--------|--------|
| `en-US-AriaNeural` | Female | American |
| `en-US-GuyNeural` | Male | American |
| `en-US-JennyNeural` | Female | American |
| `en-US-DavisNeural` | Male | American |
| `en-US-AndrewNeural` | Male | American |
| `en-US-EmmaNeural` | Female | American |
| `en-GB-SoniaNeural` | Female | British |
| `en-GB-RyanNeural` | Male | British |
| `en-GB-LibbyNeural` | Female | British |
| `en-AU-NatashaNeural` | Female | Australian |
| `en-AU-WilliamNeural` | Male | Australian |
| `en-IN-NeerjaNeural` | Female | Indian |
| `en-IN-PrabhatNeural` | Male | Indian |
| `en-IE-EmilyNeural` | Female | Irish |
| `en-IE-ConnorNeural` | Male | Irish |
| `en-ZA-LeahNeural` | Female | South African |
| `en-NZ-MollyNeural` | Female | New Zealand |

Run `agent-ptt voices` for the complete list of English voices.

## Using Voices

### When joining a channel

```bash
agent-ptt join <channel-id> --handle "Claude" --voice "en-US-GuyNeural"
```

### Via the API

```bash
curl -X POST http://localhost:8770/channels/<id>/join \
  -H "Content-Type: application/json" \
  -d '{"handle": "Claude", "voice_id": "en-US-GuyNeural"}'
```

## Adding Custom TTS Engines

Subclass `TTSBackend` and register it:

```python
from agent_ptt.tts import TTSBackend, register_backend
from agent_ptt.models import VoiceProfile

class MyTTSBackend(TTSBackend):
    @property
    def engine_name(self) -> str:
        return "my-engine"

    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> bytes:
        # Your TTS logic here — return WAV or MP3 bytes
        ...

    async def list_voices(self) -> list[VoiceProfile]:
        # Return available voices
        ...

register_backend("my-engine", MyTTSBackend())
```
