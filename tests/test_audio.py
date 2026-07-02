"""AudioMixer queueing and spectator fan-out (no actual playback)."""

from agent_ptt.audio import AudioMixer, _mixers, get_mixer, remove_mixer


def test_register_and_unregister_listener():
    mixer = AudioMixer()
    q = mixer.register_stream_listener()
    assert q in mixer._stream_listeners
    mixer.unregister_stream_listener(q)
    assert q not in mixer._stream_listeners
    # Unregistering twice is a no-op
    mixer.unregister_stream_listener(q)


async def test_broadcast_fans_out_to_all_listeners():
    mixer = AudioMixer()
    q1 = mixer.register_stream_listener()
    q2 = mixer.register_stream_listener()

    await mixer._broadcast_to_listeners(b"chunk")

    assert q1.get_nowait() == b"chunk"
    assert q2.get_nowait() == b"chunk"


async def test_enqueue():
    mixer = AudioMixer()
    await mixer.enqueue(b"audio", "Claude")
    assert mixer._queue.get_nowait() == (b"audio", "Claude")


async def test_get_mixer_caches_per_channel():
    mixer = get_mixer("chan-1")
    assert get_mixer("chan-1") is mixer
    assert get_mixer("chan-2") is not mixer


async def test_remove_mixer():
    mixer = get_mixer("chan-1")
    remove_mixer("chan-1")
    assert "chan-1" not in _mixers
    assert mixer._running is False
    # Removing a missing channel is a no-op
    remove_mixer("chan-1")
