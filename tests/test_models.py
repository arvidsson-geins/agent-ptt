"""Pydantic schema defaults and ORM-to-Pydantic conversion."""

from datetime import UTC, datetime

from agent_ptt.models import (
    Channel,
    Message,
    MessageDB,
    ParticipantKey,
    ParticipantKeyDB,
    VoiceProfile,
    VoiceProfileDB,
)


def test_channel_defaults():
    a = Channel(name="Room A")
    b = Channel(name="Room B")
    assert a.channel_id != b.channel_id
    assert a.participants == {}
    assert a.messages == []
    assert a.created_at is not None


def test_participant_key_defaults():
    key = ParticipantKey(handle="Claude")
    assert key.key_id
    assert key.voice_id is None
    assert key.channel_id is None


def test_voice_profile_defaults():
    profile = VoiceProfile(display_name="Aria")
    assert profile.engine == "edge-tts"
    assert profile.settings == {}


def test_voice_profile_from_orm():
    # Column defaults (e.g. created_at) only apply at INSERT, so set them here
    db_row = VoiceProfileDB(
        voice_id="en-US-AriaNeural",
        display_name="Aria",
        engine="edge-tts",
        settings={"voice": "en-US-AriaNeural"},
        created_at=datetime.now(UTC),
    )
    profile = VoiceProfile.model_validate(db_row)
    assert profile.voice_id == "en-US-AriaNeural"
    assert profile.settings == {"voice": "en-US-AriaNeural"}


def test_participant_key_from_orm():
    db_row = ParticipantKeyDB(
        key_id="k1",
        handle="Claude",
        voice_id="v1",
        channel_id="c1",
        created_at=datetime.now(UTC),
    )
    key = ParticipantKey.model_validate(db_row)
    assert key.key_id == "k1"
    assert key.handle == "Claude"


def test_message_from_orm():
    db_row = MessageDB(
        message_id="m1",
        channel_id="c1",
        sender_key="k1",
        handle="Claude",
        text="hello",
        timestamp=datetime.now(UTC),
    )
    msg = Message.model_validate(db_row)
    assert msg.message_id == "m1"
    assert msg.text == "hello"
