# Roadmap: Local TTS Engines (No External Dependencies)

## Problem

Agent PTT currently relies on `edge-tts` (Microsoft's cloud service) for voice synthesis. We want to run high-quality TTS locally, on-device, with zero network calls — using the same OmniVoice engine that OmniVoice Studio uses.

## Core Insight

The OmniVoice "engine" is **not** the full OmniVoice Studio app. It's a small, cleanly separable HuggingFace `PreTrainedModel` in the `omnivoice/` package. Its entire public surface is two methods:

```python
from omnivoice.models.omnivoice import OmniVoice

model = OmniVoice.from_pretrained("k2-fsa/OmniVoice", device_map="auto", dtype=torch.float16)
audios = model.generate(text="Hello world", instruct="[gender:female][age:young]")
# -> list[torch.Tensor] at 24kHz
```

Everything else in OmniVoice Studio — FastAPI, Tauri, GPU thread pool, idle unloading, subprocess sidecars, engine registry, DSP mastering — is **orchestration**, not the engine. We don't need any of it.

## What We Keep vs. Drop

| Layer | OmniVoice Location | Agent PTT |
|-------|-------------------|-----------|
| `omnivoice/` package (model, tokenizers, generate) | `omnivoice/` | **Keep — this is the engine** |
| `OmniVoice.from_pretrained()` + `.generate()` | `model_manager.py` | **Keep — call directly** |
| Device auto-detect (CUDA/MPS/CPU) | `device_caps.py` | **Keep** (small helper) |
| HF download / cache repair | `model_manager.py` | **Drop** — `from_pretrained` already downloads |
| GPU thread pool, idle unload, torch.compile | `model_manager.py` | **Drop** — server perf, not needed |
| FastAPI, Tauri, engine registry, sidecars, DSP | `backend/`, `frontend/` | **Drop** |
| WhisperX / ASR | `asr_backend.py` | **Optional** — only for clone without `ref_text` |

## Engine API

### `OmniVoice.from_pretrained()`

```python
model = OmniVoice.from_pretrained(
    "k2-fsa/OmniVoice",       # HuggingFace checkpoint (downloads ~2.4GB on first run)
    device_map="auto",          # CUDA > MPS > CPU
    dtype=torch.float16,        # fp16 for GPU, fp32 for CPU
    load_asr=False,             # True only if cloning without ref_text
)
```

### `model.generate()`

Three modes:

```python
# Mode 1: Voice Design (instruct only — no reference audio)
audios = model.generate(
    text="Hello, I'm your AI assistant.",
    instruct="[gender:female][age:young][accent:british][tone:warm]",
    language="en",
)

# Mode 2: Voice Clone (reference audio)
audios = model.generate(
    text="Hello, I'm your AI assistant.",
    ref_audio="./reference.wav",
    ref_text="This is what I sound like.",
)

# Mode 3: Auto (model picks a voice)
audios = model.generate(text="Hello world")
```

- Returns `list[torch.Tensor]` — take `[0]`
- Sample rate: `model.sampling_rate` (24kHz)
- Tensors may be on GPU/fp16 — move to CPU and cast before writing

## Proposed Approaches

### Option A: Depend on `omnivoice` PyPI Package

The repo publishes itself as `omnivoice` on PyPI. Add it as a dependency:

```toml
dependencies = [
    "omnivoice",  # the engine package
]
```

**Pros**: No code to maintain, automatic updates
**Cons**: The PyPI package may bundle the full app's dependency list (gradio, pyannote, pyinstaller, etc.) — need to verify the wheel only contains `omnivoice/models/`

### Option B: Vendor the `omnivoice/` Directory (Recommended)

Copy just the `omnivoice/` directory into Agent PTT. Pin a minimal dependency set.

```toml
# Only what the engine actually needs
dependencies = [
    "torch>=2.4",
    "torchaudio>=2.4",
    "transformers>=5.3.0",
    "huggingface_hub",
    "soundfile",
    "numpy",
]
```

**Pros**: Slim install (~6 deps vs ~20+), full control, no app bloat
**Cons**: Must manually sync with upstream changes

### Option C: Git Subtree / Submodule

Use git subtree to pull just `omnivoice/` from the OmniVoice repo:

```bash
git subtree add --prefix=omnivoice https://github.com/debpalash/OmniVoice-Studio.git main --squash
```

**Pros**: Easy to sync with upstream, clear provenance
**Cons**: Pulls the full repo history

## Recommendation

**Option B (vendor)** for now — it's the cleanest path to zero bloat. The `omnivoice/` package is small and self-contained. Once the PyPI package is verified to be slim, switch to Option A.

## Slim Dependency Set

What the `omnivoice/` engine actually needs:

```
torch>=2.4              # model inference
torchaudio>=2.4         # audio tensor encoding
transformers>=5.3.0     # HuggingFace model loading
huggingface_hub         # model downloads
soundfile               # audio I/O
numpy                   # tensor ops
```

**Optional**: `whisperx>=3.1.0` — only needed for auto-transcribing reference clips (voice cloning without supplying `ref_text`). Always supplying `ref_text` avoids ASR entirely.

## Models Downloaded at Runtime

These are fetched from HuggingFace Hub into `~/.cache/huggingface` (relocatable via `HF_HOME` / `HF_HUB_CACHE`).

### Always required (every mode)

1. **`k2-fsa/OmniVoice`** (~2.4 GB) — the main TTS checkpoint. Provides the LLM weights **and** the text tokenizer (`AutoTokenizer.from_pretrained()`).

2. **Higgs audio tokenizer** (`HiggsAudioV2TokenizerModel` + feature extractor) — loaded in this order:
   - **First choice**: the `audio_tokenizer/` subdirectory inside the `k2-fsa/OmniVoice` snapshot — normally bundled, so no separate fetch.
   - **Fallback**: if that subdir is absent, downloads `eustlb/higgs-audio-v2-tokenizer` as a separate Hub repo.
   
   Mandatory either way — it tokenizes audio in/out and sets `model.sampling_rate`.

### Optional (one specific case)

3. **`openai/whisper-large-v3-turbo`** (~1.6 GB) — the ASR model. Downloaded **only** when `load_asr=True`, which is needed **only** to clone a voice from a reference clip *without* supplying its transcript. Not downloaded for plain TTS, voice design, or cloning where `ref_text` is provided.

### Summary

| Model | Size | When downloaded |
|-------|------|----------------|
| `k2-fsa/OmniVoice` (weights + text tokenizer) | ~2.4 GB | Always (first use) |
| Higgs audio tokenizer | bundled above | Always (bundled with main checkpoint) |
| `openai/whisper-large-v3-turbo` | ~1.6 GB | Only for clone without `ref_text` |

A minimal working setup needs just **`k2-fsa/OmniVoice`** (~2.4 GB). The Whisper ASR model is an extra ~1.6 GB that can be skipped entirely if `ref_text` is always supplied when cloning.

## Gotchas

- **First run downloads ~2.4 GB** to `~/.cache/huggingface`. Set `HF_HOME` / `HF_HUB_CACHE` to relocate.
- **dtype**: the app hardcodes `torch.float16` for GPUs. On CPU, fp16 is often slower or unsupported — `torch.float32` is safer.
- **Sample rate is 24 kHz** — read from `model.sampling_rate`, don't hardcode.
- **`generate()` returns `list[torch.Tensor]`** — take `[0]`. Tensors may be on GPU / fp16 — `.cpu().float()` before writing.
- **Clone-prompt reuse**: `model.create_voice_clone_prompt(ref_audio, ref_text)` returns a reusable `VoiceClonePrompt` object. Cache it to avoid re-processing the same reference clip.
- **Clone without `ref_text`** requires `load_asr=True` at model load time, pulling in WhisperX + ~1.6 GB Whisper model. Always supplying `ref_text` avoids this entirely.
- **License**: the app is AGPL-3.0; the bundled model weights are Apache-2.0 upstream. Distributing extracted code means minding the AGPL on any code copied from outside the `omnivoice/` model directory.

## Implementation Plan

### Phase 1: `OmniVoiceTTSBackend` (1-2 days)

Add a new TTSBackend that calls the engine directly:

```python
class OmniVoiceTTSBackend(TTSBackend):
    def __init__(self):
        self.model = None  # lazy load
    
    async def synthesize(self, text, voice_profile):
        if self.model is None:
            self.model = OmniVoice.from_pretrained(
                "k2-fsa/OmniVoice",
                device_map=get_best_device(),
                dtype=get_dtype(),
            )
        
        instruct = voice_profile.settings.get("instruct")
        ref_audio = voice_profile.settings.get("ref_audio")
        ref_text = voice_profile.settings.get("ref_text")
        
        audios = await asyncio.to_thread(
            self.model.generate,
            text=text,
            instruct=instruct,
            ref_audio=ref_audio,
            ref_text=ref_text,
        )
        
        audio = audios[0].cpu().float()
        return tensor_to_wav(audio, self.model.sampling_rate)
```

### Phase 2: Model Download CLI (1 day)

```bash
agent-ptt model download          # downloads OmniVoice checkpoint
agent-ptt model list              # shows cached models
agent-ptt model status            # shows download progress
```

### Phase 3: Voice Design CLI (1-2 days)

```bash
agent-ptt voice design --gender female --age young --accent british --name "Brit"
agent-ptt voice preview "Brit" --text "Hello there"
agent-ptt voice list
```

## Key Source References

| Concern | OmniVoice Path |
|---------|---------------|
| Engine model + `from_pretrained` / `generate` | `omnivoice/models/omnivoice.py` |
| Load flow, device selection, dtype | `backend/services/model_manager.py` |
| Engine adapter surface | `backend/services/tts_backend.py` |
| Host GPU probe (CUDA/MPS/CPU) | `backend/core/device_caps.py` |
| Package manifest | `pyproject.toml` |

## Related Docs

- [Voice Design](voice-design.md) — instruct tags, archetypes, cloning
- [Engine Integration](engine-integration.md) — technical details
