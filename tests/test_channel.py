"""Channel manager — lifecycle, participants, messaging."""

from agent_ptt import channel as ch
from agent_ptt.models import MessageDB


def test_create_and_get_channel():
    created = ch.create_channel("War Room")
    assert created.name == "War Room"
    assert ch.get_channel(created.channel_id) is created
    assert ch.get_message_queue(created.channel_id) is not None


def test_list_channels():
    assert ch.list_channels() == []
    a = ch.create_channel("A")
    b = ch.create_channel("B")
    ids = {c.channel_id for c in ch.list_channels()}
    assert ids == {a.channel_id, b.channel_id}


def test_delete_channel():
    created = ch.create_channel("Doomed")
    assert ch.delete_channel(created.channel_id) is True
    assert ch.get_channel(created.channel_id) is None
    assert ch.get_message_queue(created.channel_id) is None
    assert ch.delete_channel("nonexistent") is False


def test_join_channel():
    created = ch.create_channel("Room")
    key = ch.join_channel(created.channel_id, "Claude", "en-US-AriaNeural")
    assert key is not None
    assert key.handle == "Claude"
    assert key.channel_id == created.channel_id
    assert created.participants[key.key_id] is key


def test_join_unknown_channel():
    assert ch.join_channel("nonexistent", "Claude") is None


def test_join_persists_key(db_session):
    created = ch.create_channel("Room")
    key = ch.join_channel(created.channel_id, "Claude", db=db_session)
    from agent_ptt.models import ParticipantKeyDB

    row = db_session.get(ParticipantKeyDB, key.key_id)
    assert row is not None
    assert row.handle == "Claude"


def test_leave_channel_and_get_participant():
    created = ch.create_channel("Room")
    key = ch.join_channel(created.channel_id, "Claude")
    assert ch.get_participant(key.key_id) is key
    assert ch.leave_channel(key.key_id) is True
    assert ch.get_participant(key.key_id) is None
    assert ch.leave_channel(key.key_id) is False


async def test_send_message():
    created = ch.create_channel("Room")
    key = ch.join_channel(created.channel_id, "Claude")

    msg = await ch.send_message(key.key_id, "hello world")

    assert msg is not None
    assert msg.handle == "Claude"
    assert ch.get_history(created.channel_id) == [msg]
    queue = ch.get_message_queue(created.channel_id)
    assert queue.get_nowait() is msg


async def test_send_message_unknown_key():
    ch.create_channel("Room")
    assert await ch.send_message("nonexistent", "hello") is None


async def test_send_message_persists(db_session):
    created = ch.create_channel("Room")
    key = ch.join_channel(created.channel_id, "Claude")

    msg = await ch.send_message(key.key_id, "for the record", db=db_session)

    row = db_session.get(MessageDB, msg.message_id)
    assert row is not None
    assert row.text == "for the record"


def test_get_history_unknown_channel():
    assert ch.get_history("nonexistent") == []
