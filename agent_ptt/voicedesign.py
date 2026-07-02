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

# OmniVoice instruct vocabulary — comma-separated plain items, validated
# against the model's _INSTRUCT_VALID_EN set at generate() time
GENDERS = ["male", "female"]
AGES = ["teenager", "young adult", "middle-aged", "elderly"]
ACCENTS = [
    "american accent",
    "australian accent",
    "british accent",
    "canadian accent",
    "indian accent",
]
PITCHES = ["very low pitch", "low pitch", "moderate pitch", "high pitch", "very high pitch"]

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
    """Deterministically generate an OmniVoice instruct string from a handle.

    Format: comma + space separated items, e.g.
    "female, young adult, british accent, low pitch".
    """
    h = _handle_hash(handle)

    return ", ".join(
        [
            GENDERS[h % len(GENDERS)],
            AGES[(h >> 8) % len(AGES)],
            ACCENTS[(h >> 16) % len(ACCENTS)],
            PITCHES[(h >> 24) % len(PITCHES)],
        ]
    )


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
