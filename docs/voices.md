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
| `engine` | string | TTS engine identifier (`edge-tts`, `system`) |
| `settings` | object | Engine-specific parameters |
| `created_at` | datetime | When the profile was created |

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
