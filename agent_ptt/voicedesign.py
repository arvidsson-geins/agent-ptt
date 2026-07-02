"""Deterministic voice design — hash a handle into a stable, unique voice.

When a participant joins without picking a voice, we design one from
their handle and pin it in the database, so the same handle always
sounds the same across sessions. Zero dependencies (SHA-256 only);
an LLM-based designer can later replace the hash while keeping the
same pinning flow.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from agent_ptt.models import PinnedVoiceDB, VoiceProfile
from agent_ptt.voices import get_voice_profile, save_voice_profile

logger = logging.getLogger(__name__)

# OmniVoice instruct vocabulary — comma-separated plain items, validated
# against the model's _INSTRUCT_VALID_EN set at generate() time
GENDERS = ["male", "female"]
AGES = ["teenager", "young adult", "middle-aged", "elderly"]
ACCENTS = [
    "american accent",
    "australian accent",
    "british accent",
    "canadian accent",
    "chinese accent",
    "indian accent",
    "japanese accent",
    "korean accent",
    "portuguese accent",
    "russian accent",
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


def _design_best_voice(handle: str, engine: str) -> tuple[VoiceProfile, str]:
    """Design a voice using the LLM designer when available, else the hash.

    Returns (profile, source) where source is "llm" or "hash".
    """
    if engine == "omnivoice":
        try:
            from agent_ptt.designer import designer_available, get_designer

            if designer_available():
                instruct = get_designer().design_instruct(handle)
                profile = VoiceProfile(
                    voice_id=f"auto-{handle.lower()}",
                    display_name=f"{handle}'s Voice",
                    engine="omnivoice",
                    settings={"instruct": instruct},
                )
                return profile, "llm"
        except Exception as e:
            logger.warning(f"LLM voice design failed for [{handle}], using hash: {e}")

    return design_voice(handle, engine), "hash"


def _pin_voice(handle: str, profile: VoiceProfile, source: str, db: Session) -> None:
    save_voice_profile(profile, db)
    db.merge(
        PinnedVoiceDB(
            handle=handle.lower(),
            voice_id=profile.voice_id,
            source=source,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()


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

    profile, source = _design_best_voice(handle, engine)
    _pin_voice(handle, profile, source, db)
    return profile


def redesign_pinned_voice(
    handle: str,
    db: Session,
    engine: str = "edge-tts",
) -> VoiceProfile:
    """Design a fresh voice for a handle, replacing any existing pin."""
    profile, source = _design_best_voice(handle, engine)
    _pin_voice(handle, profile, source, db)
    return profile


def list_pinned_voices(db: Session) -> list[dict]:
    """All pinned voices with their profile settings, newest first."""
    from sqlalchemy import select

    pins = db.scalars(select(PinnedVoiceDB)).all()
    result = []
    for pin in sorted(pins, key=lambda p: p.created_at or datetime.min, reverse=True):
        profile = get_voice_profile(pin.voice_id, db)
        result.append(
            {
                "handle": pin.handle,
                "voice_id": pin.voice_id,
                "source": pin.source,
                "engine": profile.engine if profile else None,
                "settings": profile.settings if profile else {},
            }
        )
    return result
