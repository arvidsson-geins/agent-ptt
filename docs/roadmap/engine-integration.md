# Roadmap: Engine Integration (Technical Plan)

## Overview

The OmniVoice engine is a standard HuggingFace `PreTrainedModel`. Integration into Agent PTT is straightforward — no subprocess sidecars, no engine registry, no GPU pool. Just load the model and call `generate()`.

## Architecture

```
agent_ptt/tts.py
    │
    ├── EdgeTTSBackend          ← cloud (existing)
    ├── SystemTTSBackend        ← offline fallback (existing)
    └── OmniVoiceTTSBackend     ← local neural TTS (new)
            │
            └── omnivoice.OmniVoice.from_pretrained()
                    │
                    └── model.generate(text, instruct=..., ref_audio=...)
                            │
                            └── torch.Tensor @ 24kHz → WAV bytes
```

## Implementation

### New File: `agent_ptt/engines/omnivoice.py`

```python
"""OmniVoice local TTS engine — runs the model directly, no external service."""

import asyncio
import io
import logging
from pathlib import Path

import numpy as np
import torch
import torchaudio

from agent_ptt.models import VoiceProfile
from agent_ptt.tts import TTSBackend

logger = logging.getLogger(__name__)


def get_best_device() -> str:
    """Auto-detect the best compute device."""
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_dtype(device: str) -> torch.dtype:
    """fp16 for GPU, fp32 for CPU (fp16 is slower/unsupported on CPU)."""
    return torch.float16 if device != "cpu" else torch.float32


def tensor_to_wav(audio: torch.Tensor, sample_rate: int) -> bytes:
    """Convert a torch audio tensor to WAV bytes."""
    audio = audio.cpu().float()
    if audio.dim() == 1:
        audio = audio.unsqueeze(0)  # [samples] -> [1, samples]
    
    buf = io.BytesIO()
    torchaudio.save(buf, audio, sample_rate, format="wav")
    return buf.getvalue()


class OmniVoiceTTSBackend(TTSBackend):
    """Local neural TTS using the OmniVoice model.
    
    Loads the model on first use (~2.4GB download on first run).
    Supports voice design via instruct strings and voice cloning
    via reference audio.
    """

    def __init__(self, checkpoint: str = "k2-fsa/OmniVoice"):
        self.checkpoint = checkpoint
        self._model = None

    @property
    def engine_name(self) -> str:
        return "omnivoice"

    def _load_model(self):
        """Lazy-load the model on first use."""
        if self._model is None:
            from omnivoice.models.omnivoice import OmniVoice
            
            device = get_best_device()
            dtype = get_dtype(device)
            
            logger.info(
                f"Loading OmniVoice model from {self.checkpoint} "
                f"(device={device}, dtype={dtype})"
            )
            self._model = OmniVoice.from_pretrained(
                self.checkpoint,
                device_map=device,
                dtype=dtype,
                load_asr=False,  # no ASR unless cloning without ref_text
            )
            logger.info("OmniVoice model loaded")
        return self._model

    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> bytes:
        """Synthesize text to WAV audio bytes."""
        model = await asyncio.to_thread(self._load_model)
        
        settings = voice_profile.settings
        
        # Build generate kwargs from voice profile
        kwargs = {"text": text}
        
        if instruct := settings.get("instruct"):
            kwargs["instruct"] = instruct
        
        if ref_audio := settings.get("ref_audio"):
            kwargs["ref_audio"] = ref_audio
            if ref_text := settings.get("ref_text"):
                kwargs["ref_text"] = ref_text
        
        if language := settings.get("language"):
            kwargs["language"] = language
        
        if speed := settings.get("speed"):
            kwargs["speed"] = float(speed)
        
        # Run inference in thread pool (blocking)
        audios = await asyncio.to_thread(model.generate, **kwargs)
        
        # Take the first result, convert to WAV
        audio = audios[0]
        sample_rate = getattr(model, "sampling_rate", 24000)
        
        return tensor_to_wav(audio, sample_rate)

    async def list_voices(self) -> list[VoiceProfile]:
        """Return available voice archetypes."""
        # Built-in archetypes using instruct strings
        archetypes = [
            ("narrator", "Epic Narrator",
             "[gender:male][age:adult][accent:american][tone:authoritative]"),
            ("podcaster", "Friendly Podcaster",
             "[gender:male][age:adult][accent:american][tone:conversational]"),
            ("newscaster", "News Anchor",
             "[gender:female][age:adult][accent:american][tone:professional]"),
            ("storyteller", "Warm Storyteller",
             "[gender:female][age:adult][accent:british][tone:warm]"),
            ("assistant", "AI Assistant",
             "[gender:female][age:young][accent:american][tone:friendly]"),
            ("professor", "Distinguished Professor",
             "[gender:male][age:senior][accent:british][tone:authoritative]"),
        ]
        return [
            VoiceProfile(
                voice_id=vid,
                display_name=name,
                engine="omnivoice",
                settings={"instruct": instruct},
            )
            for vid, name, instruct in archetypes
        ]
```

### Registration in `tts.py`

```python
# Only register if omnivoice is installed
try:
    from agent_ptt.engines.omnivoice import OmniVoiceTTSBackend
    register_backend("omnivoice", OmniVoiceTTSBackend())
except ImportError:
    pass  # omnivoice not installed — skip
```

### Voice Profile Schema for OmniVoice

```json
{
  "voice_id": "narrator",
  "display_name": "Epic Narrator",
  "engine": "omnivoice",
  "settings": {
    "instruct": "[gender:male][age:adult][accent:american][tone:authoritative]",
    "language": "en",
    "speed": 1.0,
    "ref_audio": null,
    "ref_text": null
  }
}
```

## Device Detection

```python
# Priority: CUDA > MPS (Apple Silicon) > CPU
def get_best_device():
    if torch.cuda.is_available():
        return "cuda"              # NVIDIA GPU
    if torch.backends.mps.is_available():
        return "mps"               # Apple Silicon
    return "cpu"                   # Fallback

# dtype: fp16 for GPU speed, fp32 for CPU compatibility
def get_dtype(device):
    return torch.float16 if device != "cpu" else torch.float32
```

## Dependencies

The OmniVoice engine adds these to `pyproject.toml` as optional extras:

```toml
[project.optional-dependencies]
omnivoice = [
    "torch>=2.4",
    "torchaudio>=2.4",
    "transformers>=5.3.0",
    "huggingface_hub",
    "omnivoice",            # or vendored omnivoice/ package
]

# Install: uv sync --extra omnivoice
```

This keeps the base install lightweight (edge-tts only) while allowing opt-in to local inference.

## CLI Additions

### Model Management

```bash
# Download the model (~2.4GB)
agent-ptt model download

# Check model status
agent-ptt model status
# ✅ OmniVoice v1 — 2.4 GB — cached at ~/.cache/huggingface/...

# List cached models
agent-ptt model list
```

### Voice Design

```bash
# Design a voice with instruct tags
agent-ptt voice design \
  --gender female \
  --age young \
  --accent british \
  --tone warm \
  --name "Brit Assistant"

# Preview a designed voice
agent-ptt voice preview "Brit Assistant" --text "Hello, lovely to meet you"

# Use in a channel
agent-ptt join <channel> --handle "Agent" --voice "Brit Assistant"
```

## Models Downloaded at Runtime

| Model | Size | When |
|-------|------|------|
| `k2-fsa/OmniVoice` (weights + text tokenizer + Higgs audio tokenizer) | ~2.4 GB | Always (first use) |
| `eustlb/higgs-audio-v2-tokenizer` | small | Only if `audio_tokenizer/` missing from main checkpoint |
| `openai/whisper-large-v3-turbo` | ~1.6 GB | Only for clone without `ref_text` |

The Higgs audio tokenizer is normally **bundled** inside the main `k2-fsa/OmniVoice` snapshot (as `audio_tokenizer/` subdir). It only fetches separately if that subdir is missing.

## Gotchas

| Issue | Mitigation |
|-------|-----------|
| First run downloads ~2.4 GB | Show progress bar, cache in `~/.cache/huggingface`. Set `HF_HOME` to relocate |
| fp16 slow/broken on CPU | Auto-detect device, use `torch.float32` for CPU |
| `generate()` returns `list[Tensor]` | Take `[0]`, `.cpu().float()` before WAV encoding |
| Sample rate is 24 kHz | Read from `model.sampling_rate`, don't hardcode |
| Clone without `ref_text` needs ASR | Require `ref_text` to avoid WhisperX + ~1.6 GB model |
| Clone-prompt reuse | Cache `model.create_voice_clone_prompt()` result to avoid re-processing same reference clip |
| AGPL-3.0 license on app code | Only copy from `omnivoice/` dir (model weights are Apache-2.0) |

## Related Docs

- [Local TTS Engines](local-tts-engines.md) — strategic overview
- [Voice Design](voice-design.md) — instruct system details
