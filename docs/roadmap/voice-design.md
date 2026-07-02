# Roadmap: Voice Design System

## Problem

We want agents to have unique, designed voices — without depending on edge-tts or any cloud service. OmniVoice's engine supports voice design via **instruct strings** and **voice cloning** from reference audio.

## How Voice Design Works

The OmniVoice model accepts an `instruct` parameter that describes the desired voice. The model interprets these tags during generation and produces speech matching the description.

### Three Modes

```python
# 1. Voice Design — instruct string, no reference audio
audios = model.generate(
    text="Hello world",
    instruct="[gender:female][age:young][accent:british][tone:warm]",
)

# 2. Voice Clone — reference audio + transcript
audios = model.generate(
    text="Hello world",
    ref_audio="./my-voice.wav",     # 5-30 second clip
    ref_text="This is what I said in the clip.",
)

# 3. Auto — model picks a default voice
audios = model.generate(text="Hello world")
```

### Instruct Tags

| Tag | Values | Description |
|-----|--------|-------------|
| `gender` | `male`, `female` | Voice gender |
| `age` | `young`, `adult`, `senior` | Perceived age |
| `accent` | `american`, `british`, `australian`, `indian`, ... | Regional accent |
| `tone` | `warm`, `professional`, `casual`, `authoritative`, `friendly`, `conversational` | Emotional quality |
| `pace` | `slow`, `moderate`, `fast` | Speaking speed |
| `pitch` | `low`, `medium`, `high` | Voice pitch range |

Example:
```
[gender:male][age:adult][accent:british][tone:authoritative][pace:moderate]
```

## Voice Profile Schema

```json
{
  "voice_id": "custom-narrator",
  "display_name": "Epic Narrator",
  "engine": "omnivoice",
  "settings": {
    "instruct": "[gender:male][age:adult][accent:british][tone:authoritative]",
    "language": "en",
    "speed": 1.0,
    "ref_audio": null,
    "ref_text": null
  }
}
```

For voice cloning:
```json
{
  "voice_id": "my-clone",
  "display_name": "My Voice Clone",
  "engine": "omnivoice",
  "settings": {
    "ref_audio": "/path/to/reference.wav",
    "ref_text": "This is what I said in the reference clip.",
    "language": "en"
  }
}
```

## Implementation Phases

### Phase 1: Instruct-Based Voice Profiles

Extend voice profile `settings` to include instruct strings. When an agent joins with `engine: "omnivoice"`, the instruct drives voice generation.

```bash
agent-ptt join <channel> \
  --handle "Claude" \
  --voice "narrator" \
  --engine omnivoice
```

### Phase 2: Built-In Archetypes

Ship a curated gallery of voice presets:

| Archetype | Instruct |
|-----------|----------|
| Narrator | `[gender:male][age:adult][accent:american][tone:authoritative]` |
| Podcaster | `[gender:male][age:adult][accent:american][tone:conversational]` |
| News Anchor | `[gender:female][age:adult][accent:american][tone:professional]` |
| Storyteller | `[gender:female][age:adult][accent:british][tone:warm]` |
| Assistant | `[gender:female][age:young][accent:american][tone:friendly]` |
| Professor | `[gender:male][age:senior][accent:british][tone:authoritative]` |

```bash
agent-ptt voices --engine omnivoice
# Shows the archetype table
```

### Phase 3: Voice Designer CLI

Interactive voice design:

```bash
# Design a new voice
agent-ptt voice design \
  --gender female \
  --age young \
  --accent australian \
  --tone friendly \
  --name "Aussie Agent"

# Preview it (generates a test clip and plays through speakers)
agent-ptt voice preview "Aussie Agent" \
  --text "G'day! Let's have a chat about the architecture."

# Save it to the database
agent-ptt voice save "Aussie Agent"

# List all saved voices
agent-ptt voice list

# Delete a voice
agent-ptt voice delete "Aussie Agent"
```

### Phase 4: Voice Cloning

Clone a voice from a reference audio clip:

```bash
# Clone from a WAV file (must supply transcript)
agent-ptt voice clone \
  --reference ./my-voice-sample.wav \
  --transcript "This is what I said in the recording." \
  --name "My Clone"

# Use the clone in a channel
agent-ptt join <channel> --handle "Me" --voice "My Clone"
```

Note: cloning without `--transcript` would require the WhisperX ASR model. Always supplying the transcript keeps the install slim.

## Storage

Voices are persisted in the SQLite database (`voice_profiles` table). The voice profile schema is the same for all engines — only the `settings` dict changes.

For voice clones, the reference audio file path is stored in `settings.ref_audio`. The file itself stays where it is (not copied into the database).

## Related Docs

- [Local TTS Engines](local-tts-engines.md) — strategic approach
- [Engine Integration](engine-integration.md) — technical implementation
