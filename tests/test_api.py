"""REST + WebSocket endpoints via TestClient, with TTS and playback faked."""

import time

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import FAKE_AUDIO


def _create_channel(client, name="Test Room") -> str:
    return client.post("/channels", json={"name": name}).json()["channel_id"]


def _join(client, channel_id, handle="Claude", voice_id="en-US-AriaNeural") -> str:
    resp = client.post(
        f"/channels/{channel_id}/join",
        json={"handle": handle, "voice_id": voice_id},
    )
    return resp.json()["key_id"]


def _wait_for(condition, timeout=5.0) -> bool:
    """Poll until condition() is truthy; the app loop runs in TestClient's thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


# ---------------------------------------------------------------------------
# REST
# ---------------------------------------------------------------------------


def test_create_channel(client):
    resp = client.post("/channels", json={"name": "War Room"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "War Room"
    assert body["channel_id"]


def test_list_channels(client):
    assert client.get("/channels").json() == []
    channel_id = _create_channel(client)
    listed = client.get("/channels").json()
    assert [c["channel_id"] for c in listed] == [channel_id]


def test_get_channel_detail(client):
    channel_id = _create_channel(client)
    resp = client.get(f"/channels/{channel_id}")
    assert resp.status_code == 200
    assert resp.json()["channel_id"] == channel_id


def test_get_unknown_channel(client):
    assert client.get("/channels/nonexistent").status_code == 404


def test_join_channel(client):
    channel_id = _create_channel(client)
    resp = client.post(
        f"/channels/{channel_id}/join",
        json={"handle": "Claude", "voice_id": "en-US-AriaNeural"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["handle"] == "Claude"
    assert body["channel_id"] == channel_id
    assert body["key_id"]


def test_join_unknown_channel(client):
    resp = client.post("/channels/nonexistent/join", json={"handle": "Claude"})
    assert resp.status_code == 404


def test_leave_channel(client):
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id)
    resp = client.post(f"/channels/{channel_id}/leave", params={"key_id": key_id})
    assert resp.status_code == 200
    assert resp.json() == {"status": "left"}


def test_leave_with_unknown_key(client):
    channel_id = _create_channel(client)
    resp = client.post(f"/channels/{channel_id}/leave", params={"key_id": "nonexistent"})
    assert resp.status_code == 404


def test_history_empty(client):
    channel_id = _create_channel(client)
    assert client.get(f"/channels/{channel_id}/history").json() == []


# ---------------------------------------------------------------------------
# Agent WebSocket
# ---------------------------------------------------------------------------


def test_ws_unknown_channel_rejected(client):
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/channels/nonexistent/ws"),
    ):
        pass
    assert exc_info.value.code == 4004


def test_ws_invalid_key_rejected(client):
    channel_id = _create_channel(client)
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/channels/{channel_id}/ws?key=bogus"),
    ):
        pass
    assert exc_info.value.code == 4001


def test_ws_send_message_broadcasts(client):
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id)

    with client.websocket_connect(f"/channels/{channel_id}/ws?key={key_id}") as ws:
        ws.send_json({"type": "message", "text": "hello channel"})
        received = ws.receive_json()

    assert received["type"] == "message"
    assert received["handle"] == "Claude"
    assert received["text"] == "hello channel"

    history = client.get(f"/channels/{channel_id}/history").json()
    assert [m["text"] for m in history] == ["hello channel"]


def test_ws_join_announced_to_others(client):
    channel_id = _create_channel(client)
    key1 = _join(client, channel_id, handle="Claude")
    key2 = _join(client, channel_id, handle="GPT")

    with (
        client.websocket_connect(f"/channels/{channel_id}/ws?key={key1}") as ws1,
        client.websocket_connect(f"/channels/{channel_id}/ws?key={key2}"),
    ):
        announcement = ws1.receive_json()

    assert announcement["type"] == "system"
    assert announcement["text"] == "GPT joined the channel"


def test_ws_message_reaches_tts_and_mixer(client, fake_tts, fake_mixer):
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id)

    with client.websocket_connect(f"/channels/{channel_id}/ws?key={key_id}") as ws:
        ws.send_json({"type": "message", "text": "speak this"})
        ws.receive_json()
        assert _wait_for(lambda: fake_mixer.enqueued), "TTS worker never enqueued audio"

    assert [text for text, _voice in fake_tts.calls] == ["speak this"]
    assert fake_mixer.enqueued == [(FAKE_AUDIO, "Claude")]


# ---------------------------------------------------------------------------
# Spectator audio WebSocket
# ---------------------------------------------------------------------------


def test_spectator_unknown_channel_rejected(client):
    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/channels/nonexistent/audio"),
    ):
        pass
    assert exc_info.value.code == 4004


def test_spectator_receives_audio(client, fake_mixer):
    channel_id = _create_channel(client)
    key_id = _join(client, channel_id)

    with (
        client.websocket_connect(f"/channels/{channel_id}/audio") as spectator,
        client.websocket_connect(f"/channels/{channel_id}/ws?key={key_id}") as ws,
    ):
        ws.send_json({"type": "message", "text": "listen to this"})
        ws.receive_json()
        audio_bytes = spectator.receive_bytes()

    assert audio_bytes == FAKE_AUDIO
