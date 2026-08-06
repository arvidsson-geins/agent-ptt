"""Channel manager — create, join, send, leave.

Channels live in memory while the server runs, and are mirrored to the
database so a restart doesn't take the room down with it: on startup the
server restores every channel, its participants and its transcript, and
the keys agents are already holding keep working.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from agent_ptt.models import (
    Channel,
    ChannelDB,
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


def create_channel(name: str, db: Session | None = None) -> Channel:
    """Create a new named channel, persisting it if a session is provided."""
    channel = Channel(name=name)
    _channels[channel.channel_id] = channel
    _message_queues[channel.channel_id] = asyncio.Queue()

    if db is not None:
        db.merge(
            ChannelDB(
                channel_id=channel.channel_id,
                name=channel.name,
                created_at=channel.created_at,
            )
        )
        db.commit()

    return channel


def list_channels() -> list[Channel]:
    """List all active channels."""
    return list(_channels.values())


def get_channel(channel_id: str) -> Channel | None:
    """Get a channel by ID."""
    return _channels.get(channel_id)


def delete_channel(channel_id: str, db: Session | None = None) -> bool:
    """Delete a channel. Returns True if it existed."""
    removed = _channels.pop(channel_id, None)
    _message_queues.pop(channel_id, None)

    if db is not None:
        row = db.get(ChannelDB, channel_id)
        if row is not None:
            db.delete(row)
            db.commit()

    return removed is not None


def restore_channels(db: Session) -> list[Channel]:
    """Rebuild the in-memory registry from the database.

    Called once on startup. Participants are restored with the keys they
    were issued, so an agent that joined before the restart can carry on
    posting without noticing it happened.
    """
    restored: list[Channel] = []

    for row in db.query(ChannelDB).order_by(ChannelDB.created_at).all():
        if row.channel_id in _channels:
            continue

        channel = Channel(
            channel_id=row.channel_id,
            name=row.name,
            created_at=_as_utc(row.created_at),
        )

        for key_row in (
            db.query(ParticipantKeyDB).filter(ParticipantKeyDB.channel_id == row.channel_id).all()
        ):
            channel.participants[key_row.key_id] = ParticipantKey(
                key_id=key_row.key_id,
                handle=key_row.handle,
                voice_id=key_row.voice_id,
                channel_id=key_row.channel_id,
                created_at=_as_utc(key_row.created_at),
            )

        for msg_row in (
            db.query(MessageDB)
            .filter(MessageDB.channel_id == row.channel_id)
            .order_by(MessageDB.timestamp)
            .all()
        ):
            channel.messages.append(
                Message(
                    message_id=msg_row.message_id,
                    channel_id=msg_row.channel_id,
                    sender_key=msg_row.sender_key,
                    handle=msg_row.handle,
                    text=msg_row.text,
                    timestamp=_as_utc(msg_row.timestamp),
                )
            )

        _channels[channel.channel_id] = channel
        _message_queues[channel.channel_id] = asyncio.Queue()
        restored.append(channel)

    return restored


def _as_utc(value: datetime | None) -> datetime:
    """SQLite hands back naive datetimes; they were always UTC."""
    if value is None:
        return datetime.now(UTC)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


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
