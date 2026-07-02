# Roadmap: Auto Voice Designer (LLM-Powered)

## Concept

When an agent joins a channel without specifying a voice, a small local LLM generates a **unique voice instruct** based on the agent's handle/name. The instruct is pinned to that handle in the database, so the agent always sounds the same across sessions.

```
Agent "Claude" joins → LLM generates voice → pinned forever
Agent "GPT" joins    → LLM generates voice → pinned forever
Agent "Krille" joins → LLM generates voice → pinned forever
```

No manual voice selection needed. Every participant gets a distinctive, consistent voice automatically.

## How It Works

### Flow

```
1. Agent joins channel with handle "Claude"
2. System checks DB: does "Claude" have a pinned voice?
   ├── YES → use the stored voice instruct
   └── NO  → run auto-designer:
             a. Small LLM generates instruct from the handle
             b. Voice instruct is saved to DB, pinned to handle
             c. OmniVoice synthesizes with that instruct
3. All future "Claude" messages use the same voice
```

### LLM Prompt

The small LLM gets a simple prompt:

```
You are a voice casting director. Given a character name, generate a unique
voice description using exactly these tags:

Tags: [gender:male|female] [age:young|adult|senior] [accent:american|british|australian|indian|irish]
      [tone:warm|professional|casual|authoritative|friendly|conversational]
      [pace:slow|moderate|fast] [pitch:low|medium|high]

Rules:
- Use ALL tags exactly once
- Make the voice match the "vibe" of the name
- Be creative — no two names should get the same combination

Name: {handle}

Voice instruct:
```

### Example Outputs

| Handle | Generated Instruct |
|--------|-------------------|
| Claude | `[gender:male][age:adult][accent:british][tone:warm][pace:moderate][pitch:medium]` |
| GPT | `[gender:male][age:young][accent:american][tone:professional][pace:fast][pitch:medium]` |
| Aria | `[gender:female][age:young][accent:american][tone:friendly][pace:moderate][pitch:high]` |
| Professor Oak | `[gender:male][age:senior][accent:british][tone:authoritative][pace:slow][pitch:low]` |
| Sakura | `[gender:female][age:young][accent:australian][tone:conversational][pace:moderate][pitch:high]` |

## LLM Options

The LLM needs to be **small, fast, and local** — it only generates ~20 tokens (one instruct string). This is a one-shot task, no conversation needed.

| Model | Size | Speed | How to run |
|-------|------|-------|------------|
| `Qwen2.5-0.5B` | ~500 MB | Instant | `transformers` / `llama-cpp-python` |
| `SmolLM2-360M` | ~360 MB | Instant | `transformers` / `llama-cpp-python` |
| `Phi-3-mini` | ~2.3 GB | Fast | `transformers` / `llama-cpp-python` |
| `TinyLlama-1.1B` | ~600 MB | Instant | `transformers` / `llama-cpp-python` |

Even the smallest models (360-500 MB) are more than capable of this task — it's just tag selection from a fixed vocabulary.

### Alternative: No LLM (Deterministic Hash)

If adding an LLM feels heavy, a **deterministic hash** could work instead:

```python
import hashlib

GENDERS = ["male", "female"]
AGES = ["young", "adult", "senior"]
ACCENTS = ["american", "british", "australian", "indian", "irish"]
TONES = ["warm", "professional", "casual", "authoritative", "friendly"]
PACES = ["slow", "moderate", "fast"]
PITCHES = ["low", "medium", "high"]

def generate_voice_instruct(handle: str) -> str:
    """Deterministically generate a unique voice instruct from a handle."""
    h = int(hashlib.sha256(handle.lower().encode()).hexdigest(), 16)
    
    gender = GENDERS[h % len(GENDERS)]
    age = AGES[(h >> 8) % len(AGES)]
    accent = ACCENTS[(h >> 16) % len(ACCENTS)]
    tone = TONES[(h >> 24) % len(TONES)]
    pace = PACES[(h >> 32) % len(PACES)]
    pitch = PITCHES[(h >> 40) % len(PITCHES)]
    
    return (
        f"[gender:{gender}][age:{age}][accent:{accent}]"
        f"[tone:{tone}][pace:{pace}][pitch:{pitch}]"
    )
```

This is zero-dependency, instant, and deterministic — same handle always gets the same voice. But it's random (hash-based), not "creative" (won't match the name's vibe).

## Recommended Approach: LLM with Hash Fallback

```python
async def get_or_create_voice(handle: str, db: Session) -> VoiceProfile:
    """Get a pinned voice for a handle, or auto-design one."""
    
    # 1. Check DB for existing pinned voice
    existing = db.query(PinnedVoice).filter_by(handle=handle.lower()).first()
    if existing:
        return existing.voice_profile
    
    # 2. Try LLM-based design (if model available)
    try:
        instruct = await llm_design_voice(handle)
    except Exception:
        # 3. Fallback to deterministic hash
        instruct = hash_design_voice(handle)
    
    # 4. Save to DB, pinned to this handle
    voice = VoiceProfile(
        voice_id=f"auto-{handle.lower()}",
        display_name=f"{handle}'s Voice",
        engine="omnivoice",
        settings={"instruct": instruct},
    )
    pinned = PinnedVoice(handle=handle.lower(), voice_profile=voice)
    db.add(pinned)
    db.commit()
    
    return voice
```

## Database Schema Addition

```sql
CREATE TABLE pinned_voices (
    handle TEXT PRIMARY KEY,           -- lowercase handle
    voice_id TEXT NOT NULL,            -- FK to voice_profiles
    instruct TEXT NOT NULL,            -- the generated instruct string
    created_at DATETIME DEFAULT NOW(), -- when the voice was designed
    source TEXT DEFAULT 'auto'         -- 'auto' (LLM), 'hash', or 'manual'
);
```

## CLI Integration

```bash
# Join without specifying voice — auto-designed!
agent-ptt join <channel> --handle "Claude"
# ✅ Joined as [Claude]
#    Voice: auto-designed [gender:male][age:adult][accent:british][tone:warm]...
#    Key: 1b71a976-...

# Re-design a handle's voice
agent-ptt voice redesign "Claude"
# 🎨 Redesigned Claude's voice
#    Old: [gender:male][age:adult][accent:british]...
#    New: [gender:male][age:young][accent:american]...

# Show all pinned voices
agent-ptt voice pinned
# ┌─────────┬──────────────────────────────────┬────────┐
# │ Handle  │ Instruct                         │ Source │
# ├─────────┼──────────────────────────────────┼────────┤
# │ claude  │ [gender:male][age:adult]...       │ auto   │
# │ gpt     │ [gender:male][age:young]...       │ auto   │
# │ krille  │ [gender:male][age:adult]...       │ manual │
# └─────────┴──────────────────────────────────┴────────┘
```

## Implementation Phases

### Phase 1: Deterministic Hash (zero dependencies)
- Implement `hash_design_voice()` — instant, no model needed
- Add `pinned_voices` table
- Auto-assign on join when no `--voice` specified
- **Effort**: 1 day

### Phase 2: LLM-Powered Design (optional)
- Add small LLM (~500 MB) as optional dependency
- LLM generates "creative" instruct matching the handle's vibe
- Fall back to hash if LLM not installed
- **Effort**: 1-2 days

### Phase 3: Voice Preview & Redesign
- `agent-ptt voice preview <handle>` — hear the auto-designed voice
- `agent-ptt voice redesign <handle>` — regenerate with new LLM output
- `agent-ptt voice pin <handle> --instruct "..."` — manually override
- **Effort**: 1 day

## Dependencies

### Phase 1 (hash only)
None — just `hashlib` (stdlib).

### Phase 2 (LLM)
```toml
[project.optional-dependencies]
voice-designer = [
    "llama-cpp-python",    # GGUF model inference (~20 tokens)
]
# Model download: ~500 MB for Qwen2.5-0.5B-GGUF
```

## Related Docs

- [Voice Design](voice-design.md) — instruct tag system
- [Local TTS Engines](local-tts-engines.md) — OmniVoice engine details
- [Engine Integration](engine-integration.md) — TTSBackend implementation
