"""Deterministic voice design — hash a handle into a stable, unique voice.

When a participant joins without picking a voice, we design one from
their handle and pin it in the database, so the same handle always
sounds the same across sessions. Zero dependencies (SHA-256 only);
an LLM-based designer can later replace the hash while keeping the
same pinning flow.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from agent_ptt.models import PinnedVoiceDB, VoiceProfile
from agent_ptt.voices import get_voice_profile, save_voice_profile

# Instruct tag vocabulary (OmniVoice voice-design tags)
GENDERS = ["male", "female"]
AGES = ["young", "adult", "senior"]
ACCENTS = ["american", "british", "australian", "indian", "irish"]
TONES = ["warm", "professional", "casual", "authoritative", "friendly"]
PACES = ["slow", "moderate", "fast"]
PITCHES = ["low", "medium", "high"]

# Curated edge-tts voices + variation ranges for the base install
EDGE_VOICES = [
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-DavisNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
]
EDGE_RATES = ["-10%", "-5%", "+0%", "+5%", "+10%"]
EDGE_PITCHES = ["-15Hz", "-8Hz", "+0Hz", "+8Hz", "+15Hz"]


def _handle_hash(handle: str) -> int:
    return int(hashlib.sha256(handle.lower().encode()).hexdigest(), 16)


def hash_instruct(handle: str) -> str:
    """Deterministically generate an OmniVoice instruct string from a handle."""
    h = _handle_hash(handle)

    gender = GENDERS[h % len(GENDERS)]
    age = AGES[(h >> 8) % len(AGES)]
    accent = ACCENTS[(h >> 16) % len(ACCENTS)]
    tone = TONES[(h >> 24) % len(TONES)]
    pace = PACES[(h >> 32) % len(PACES)]
    pitch = PITCHES[(h >> 40) % len(PITCHES)]

    return f"[gender:{gender}][age:{age}][accent:{accent}][tone:{tone}][pace:{pace}][pitch:{pitch}]"


def design_voice(handle: str, engine: str = "edge-tts") -> VoiceProfile:
    """Design a deterministic voice profile for a handle on the given engine."""
    if engine == "omnivoice":
        settings = {"instruct": hash_instruct(handle)}
    else:
        engine = "edge-tts"
        h = _handle_hash(handle)
        settings = {
            "voice": EDGE_VOICES[h % len(EDGE_VOICES)],
            "rate": EDGE_RATES[(h >> 8) % len(EDGE_RATES)],
            "pitch": EDGE_PITCHES[(h >> 16) % len(EDGE_PITCHES)],
        }

    return VoiceProfile(
        voice_id=f"auto-{handle.lower()}",
        display_name=f"{handle}'s Voice",
        engine=engine,
        settings=settings,
    )


def get_or_create_pinned_voice(
    handle: str,
    db: Session,
    engine: str = "edge-tts",
) -> VoiceProfile:
    """Return the voice pinned to a handle, designing and pinning one if absent."""
    pin = db.get(PinnedVoiceDB, handle.lower())
    if pin is not None:
        profile = get_voice_profile(pin.voice_id, db)
        if profile is not None:
            return profile

    profile = design_voice(handle, engine)
    save_voice_profile(profile, db)
    db.merge(
        PinnedVoiceDB(
            handle=handle.lower(),
            voice_id=profile.voice_id,
            source="hash",
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return profile
