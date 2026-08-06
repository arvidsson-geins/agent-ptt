"""Data models — Pydantic schemas (API) + SQLAlchemy ORM (persistence).

Voice profiles follow the same contract/shape as OmniVoice Studio
so configs are portable between the two apps.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# SQLAlchemy ORM base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""

    pass


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models (persisted)
# ---------------------------------------------------------------------------


class VoiceProfileDB(Base):
    """Persisted voice profile — survives server restart."""

    __tablename__ = "voice_profiles"

    voice_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name = Column(String, nullable=False)
    engine = Column(String, nullable=False, default="edge-tts")
    # Engine-specific settings: pitch, speed, language, etc.
    settings = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class ParticipantKeyDB(Base):
    """Persisted participation key — agent identity across sessions."""

    __tablename__ = "participant_keys"

    key_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    handle = Column(String, nullable=False)
    voice_id = Column(String, nullable=True)
    channel_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class PinnedVoiceDB(Base):
    """Auto-designed voice pinned to a handle — same voice across sessions."""

    __tablename__ = "pinned_voices"

    handle = Column(String, primary_key=True)  # lowercase
    voice_id = Column(String, nullable=False)
    source = Column(String, nullable=False, default="hash")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class ChannelDB(Base):
    """Persisted channel — so a restart doesn't orphan its transcript."""

    __tablename__ = "channels"

    channel_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))


class MessageDB(Base):
    """Optional message archive — for history retrieval after restart."""

    __tablename__ = "messages"

    message_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    channel_id = Column(String, nullable=False, index=True)
    sender_key = Column(String, nullable=False)
    handle = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Pydantic schemas (API / transport)
# ---------------------------------------------------------------------------


class VoiceProfile(BaseModel):
    """Voice profile — OmniVoice Studio compatible shape."""

    voice_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    display_name: str
    engine: str = "edge-tts"
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"from_attributes": True}


class ParticipantKey(BaseModel):
    """UUID-based participation key issued on channel join."""

    key_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    handle: str
    voice_id: str | None = None
    channel_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"from_attributes": True}


class Message(BaseModel):
    """A single message in a channel."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel_id: str
    sender_key: str
    handle: str
    text: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"from_attributes": True}


class Channel(BaseModel):
    """An active voice channel — ephemeral, lives in memory."""

    channel_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    participants: dict[str, ParticipantKey] = Field(default_factory=dict)
    messages: list[Message] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
