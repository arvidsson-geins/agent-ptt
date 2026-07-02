"""Channel manager — create, join, send, leave.

Channels are ephemeral (in-memory). Voice profiles and participation
keys are persisted via the database layer.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agent_ptt.models import (
    Channel,
    Message,
    MessageDB,
    ParticipantKey,
    ParticipantKeyDB,
)

# ---------------------------------------------------------------------------
# In-memory channel registry
# ---------------------------------------------------------------------------

_channels: dict[str, Channel] = {}
_message_queues: dict[str, asyncio.Queue[Message]] = {}


# ---------------------------------------------------------------------------
# Channel lifecycle
# ---------------------------------------------------------------------------


def create_channel(name: str) -> Channel:
    """Create a new named channel."""
    channel = Channel(name=name)
    _channels[channel.channel_id] = channel
    _message_queues[channel.channel_id] = asyncio.Queue()
    return channel


def list_channels() -> list[Channel]:
    """List all active channels."""
    return list(_channels.values())


def get_channel(channel_id: str) -> Channel | None:
    """Get a channel by ID."""
    return _channels.get(channel_id)


def delete_channel(channel_id: str) -> bool:
    """Delete a channel. Returns True if it existed."""
    removed = _channels.pop(channel_id, None)
    _message_queues.pop(channel_id, None)
    return removed is not None


# ---------------------------------------------------------------------------
# Participant lifecycle
# ---------------------------------------------------------------------------


def join_channel(
    channel_id: str,
    handle: str,
    voice_id: str | None = None,
    db: Session | None = None,
) -> ParticipantKey | None:
    """Join a channel and receive a participation key.

    The key is also persisted to the database if a session is provided.
    """
    channel = _channels.get(channel_id)
    if channel is None:
        return None

    key = ParticipantKey(
        handle=handle,
        voice_id=voice_id,
        channel_id=channel_id,
    )
    channel.participants[key.key_id] = key

    # Persist to DB
    if db is not None:
        db_key = ParticipantKeyDB(
            key_id=key.key_id,
            handle=key.handle,
            voice_id=key.voice_id,
            channel_id=key.channel_id,
            created_at=key.created_at,
        )
        db.merge(db_key)
        db.commit()

    return key


def leave_channel(key_id: str) -> bool:
    """Remove a participant by their key ID. Returns True if found."""
    for channel in _channels.values():
        if key_id in channel.participants:
            del channel.participants[key_id]
            return True
    return False


def get_participant(key_id: str) -> ParticipantKey | None:
    """Look up a participant across all channels."""
    for channel in _channels.values():
        if key_id in channel.participants:
            return channel.participants[key_id]
    return None


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


async def send_message(
    key_id: str,
    text: str,
    db: Session | None = None,
) -> Message | None:
    """Post a text message from a participant.

    Returns the Message if successful, None if the participant isn't found.
    The message is added to channel history, persisted to DB, and queued
    for TTS synthesis.
    """
    participant = get_participant(key_id)
    if participant is None or participant.channel_id is None:
        return None

    channel = _channels.get(participant.channel_id)
    if channel is None:
        return None

    msg = Message(
        channel_id=channel.channel_id,
        sender_key=key_id,
        handle=participant.handle,
        text=text,
    )

    # Add to in-memory history
    channel.messages.append(msg)

    # Queue for TTS
    queue = _message_queues.get(channel.channel_id)
    if queue is not None:
        await queue.put(msg)

    # Persist to DB
    if db is not None:
        db_msg = MessageDB(
            message_id=msg.message_id,
            channel_id=msg.channel_id,
            sender_key=msg.sender_key,
            handle=msg.handle,
            text=msg.text,
            timestamp=msg.timestamp,
        )
        db.add(db_msg)
        db.commit()

    return msg


def get_history(channel_id: str) -> list[Message]:
    """Retrieve conversation history for a channel."""
    channel = _channels.get(channel_id)
    if channel is None:
        return []
    return list(channel.messages)


def get_message_queue(channel_id: str) -> asyncio.Queue[Message] | None:
    """Get the TTS message queue for a channel."""
    return _message_queues.get(channel_id)
