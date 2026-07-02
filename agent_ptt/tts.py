"""Pluggable TTS backends — no external service dependency.

Voice profiles use the same shape as OmniVoice Studio so configs
are portable between the two apps.
"""

from __future__ import annotations

import asyncio
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from agent_ptt.models import VoiceProfile


class TTSBackend(ABC):
    """Abstract base for any TTS engine."""

    @abstractmethod
    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> bytes:
        """Synthesize text to WAV audio bytes."""
        ...

    @abstractmethod
    async def list_voices(self) -> list[VoiceProfile]:
        """Return available voices for this engine."""
        ...

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Engine identifier string."""
        ...


class EdgeTTSBackend(TTSBackend):
    """Default TTS engine using Microsoft Edge TTS (free, English voices only).

    Requires internet connectivity. Voices are identified by their
    edge-tts short name (e.g. "en-US-AriaNeural").
    """

    @property
    def engine_name(self) -> str:
        return "edge-tts"

    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> bytes:
        """Synthesize text using edge-tts."""
        import edge_tts

        voice = voice_profile.settings.get("voice", "en-US-AriaNeural")
        rate = voice_profile.settings.get("rate", "+0%")
        pitch = voice_profile.settings.get("pitch", "+0Hz")

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
        )

        # Collect audio bytes — edge-tts streams MP3 chunks
        audio_chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_chunks.append(chunk["data"])

        return b"".join(audio_chunks)

    async def list_voices(self) -> list[VoiceProfile]:
        """List available edge-tts voices."""
        import edge_tts

        voices = await edge_tts.list_voices()
        return [
            VoiceProfile(
                voice_id=v["ShortName"],
                display_name=f"{v['FriendlyName']} ({v['Locale']})",
                engine="edge-tts",
                settings={
                    "voice": v["ShortName"],
                    "locale": v["Locale"],
                    "gender": v["Gender"],
                },
            )
            for v in voices
            if v["Locale"].startswith("en-")
        ]


class SystemTTSBackend(TTSBackend):
    """Fallback TTS using pyttsx3 (fully offline, uses system voices).

    macOS: uses 'say' command / NSSpeechSynthesizer
    Windows: uses SAPI5
    Linux: uses espeak
    """

    @property
    def engine_name(self) -> str:
        return "system"

    async def synthesize(self, text: str, voice_profile: VoiceProfile) -> bytes:
        """Synthesize text using pyttsx3 (runs in thread to avoid blocking)."""
        import pyttsx3

        def _synth() -> bytes:
            engine = pyttsx3.init()

            # Apply voice settings
            voice_name = voice_profile.settings.get("voice")
            if voice_name:
                for v in engine.getProperty("voices"):
                    if voice_name in v.id or voice_name in v.name:
                        engine.setProperty("voice", v.id)
                        break

            rate = voice_profile.settings.get("rate", 200)
            engine.setProperty("rate", int(rate))

            # Save to temp file and read bytes
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                tmp_path = f.name

            engine.save_to_file(text, tmp_path)
            engine.runAndWait()

            audio_data = Path(tmp_path).read_bytes()
            Path(tmp_path).unlink(missing_ok=True)
            return audio_data

        return await asyncio.to_thread(_synth)

    async def list_voices(self) -> list[VoiceProfile]:
        """List available system voices."""
        import pyttsx3

        def _list() -> list[VoiceProfile]:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            return [
                VoiceProfile(
                    voice_id=v.id,
                    display_name=v.name,
                    engine="system",
                    settings={"voice": v.id},
                )
                for v in voices
            ]

        return await asyncio.to_thread(_list)


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

_BACKENDS: dict[str, TTSBackend] = {
    "edge-tts": EdgeTTSBackend(),
    "system": SystemTTSBackend(),
}


def has_backend(engine: str) -> bool:
    """Check whether a TTS backend is registered."""
    return engine in _BACKENDS


def get_backend(engine: str = "edge-tts") -> TTSBackend:
    """Get a TTS backend by engine name."""
    backend = _BACKENDS.get(engine)
    if backend is None:
        raise ValueError(f"Unknown TTS engine '{engine}'. Available: {list(_BACKENDS.keys())}")
    return backend


def register_backend(name: str, backend: TTSBackend) -> None:
    """Register a custom TTS backend."""
    _BACKENDS[name] = backend
