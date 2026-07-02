"""Voice profile persistence — CRUD and TTS-pipeline resolution."""

from agent_ptt.models import VoiceProfile
from agent_ptt.voices import (
    delete_voice_profile,
    get_voice_profile,
    list_voice_profiles,
    save_voice_profile,
)
from tests.test_api import _create_channel, _join, _wait_for


def _profile(voice_id="narrator", engine="edge-tts", **settings) -> VoiceProfile:
    return VoiceProfile(
        voice_id=voice_id,
        display_name=voice_id.title(),
        engine=engine,
        settings=settings or {"voice": "en-US-GuyNeural"},
    )


def test_save_and_get_roundtrip(db_session):
    saved = save_voice_profile(_profile(), db_session)
    loaded = get_voice_profile("narrator", db_session)
    assert loaded is not None
    assert loaded.voice_id == saved.voice_id
    assert loaded.engine == saved.engine
    assert loaded.settings == saved.settings


def test_get_missing_returns_none(db_session):
    assert get_voice_profile("nonexistent", db_session) is None


def test_save_is_upsert(db_session):
    save_voice_profile(_profile(), db_session)
    updated = _profile()
    updated.display_name = "Epic Narrator"
    updated.settings = {"voice": "en-GB-RyanNeural"}
    save_voice_profile(updated, db_session)

    loaded = get_voice_profile("narrator", db_session)
    assert loaded.display_name == "Epic Narrator"
    assert loaded.settings == {"voice": "en-GB-RyanNeural"}
    assert len(list_voice_profiles(db_session)) == 1


def test_list_with_engine_filter(db_session):
    save_voice_profile(_profile("a", engine="edge-tts"), db_session)
    save_voice_profile(_profile("b", engine="omnivoice"), db_session)

    assert {p.voice_id for p in list_voice_profiles(db_session)} == {"a", "b"}
    assert [p.voice_id for p in list_voice_profiles(db_session, engine="omnivoice")] == ["b"]


def test_delete(db_session):
    save_voice_profile(_profile(), db_session)
    assert delete_voice_profile("narrator", db_session) is True
    assert get_voice_profile("narrator", db_session) is None
    assert delete_voice_profile("narrator", db_session) is False


def test_tts_worker_uses_stored_profile(client, db_session, fake_tts):
    """A message from a participant whose voice_id matches a stored profile
    must be synthesized with that profile's engine and settings."""
    save_voice_profile(
        _profile("designed-voice", engine="omnivoice", instruct="[gender:female][age:young]"),
        db_session,
    )
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id, voice_id="designed-voice")

    with client.websocket_connect(f"/channels/{channel_id}/ws?key={key_id}") as ws:
        ws.send_json({"type": "message", "text": "use my designed voice"})
        ws.receive_json()
        assert _wait_for(lambda: fake_tts.calls)

    _text, voice = fake_tts.calls[0]
    assert voice.voice_id == "designed-voice"
    assert voice.engine == "omnivoice"
    assert voice.settings == {"instruct": "[gender:female][age:young]"}


def test_tts_worker_falls_back_to_raw_voice_id(client, fake_tts):
    """Without a stored profile, the raw voice_id keeps working as an edge-tts voice."""
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id, voice_id="en-US-GuyNeural")

    with client.websocket_connect(f"/channels/{channel_id}/ws?key={key_id}") as ws:
        ws.send_json({"type": "message", "text": "fallback voice"})
        ws.receive_json()
        assert _wait_for(lambda: fake_tts.calls)

    _text, voice = fake_tts.calls[0]
    assert voice.engine == "edge-tts"
    assert voice.settings == {"voice": "en-US-GuyNeural"}
