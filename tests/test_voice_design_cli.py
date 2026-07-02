"""The `voice design` and `voice preview` CLI commands.

httpx and playback are faked — no server, network, or speakers needed.
"""

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

import agent_ptt.cli as cli
from agent_ptt.models import VoiceProfile
from tests.conftest import FAKE_AUDIO, FakeTTSBackend

runner = CliRunner()


def _flat(output: str) -> str:
    return " ".join(output.split())


@pytest.fixture
def fake_post(monkeypatch):
    """Capture httpx.post payloads and reply 200."""
    calls = []

    def post(url, json=None, **kwargs):
        calls.append({"url": url, "json": json})
        return SimpleNamespace(status_code=200, json=lambda: json, text="")

    monkeypatch.setattr(cli.httpx, "post", post)
    return calls


# ---------------------------------------------------------------------------
# voice design
# ---------------------------------------------------------------------------


def test_design_full_instruct(fake_post):
    result = runner.invoke(
        cli.app,
        [
            "voice",
            "design",
            "--name",
            "Aussie Agent",
            "--gender",
            "female",
            "--age",
            "young adult",
            "--accent",
            "australian",
            "--pitch",
            "high",
        ],
    )
    assert result.exit_code == 0
    payload = fake_post[0]["json"]
    assert payload["voice_id"] == "aussie-agent"
    assert payload["display_name"] == "Aussie Agent"
    assert payload["engine"] == "omnivoice"
    assert payload["settings"] == {"instruct": "female, young adult, australian accent, high pitch"}
    assert "voice preview aussie-agent" in _flat(result.output)


def test_design_normalizes_shorthand(fake_post):
    result = runner.invoke(
        cli.app,
        ["voice", "design", "--name", "Brit", "--accent", "British", "--pitch", "LOW"],
    )
    assert result.exit_code == 0
    assert fake_post[0]["json"]["settings"]["instruct"] == "british accent, low pitch"


def test_design_explicit_id_and_whisper(fake_post):
    result = runner.invoke(
        cli.app,
        ["voice", "design", "--name", "Spooky", "--id", "ghost", "--whisper"],
    )
    assert result.exit_code == 0
    assert fake_post[0]["json"]["voice_id"] == "ghost"
    assert fake_post[0]["json"]["settings"]["instruct"] == "whisper"


def test_design_rejects_invalid_value(fake_post):
    result = runner.invoke(
        cli.app,
        ["voice", "design", "--name", "Nope", "--accent", "martian"],
    )
    assert result.exit_code == 1
    assert not fake_post
    assert "Valid options" in result.output
    assert "british" in result.output


def test_design_requires_at_least_one_attribute(fake_post):
    result = runner.invoke(cli.app, ["voice", "design", "--name", "Empty"])
    assert result.exit_code == 1
    assert not fake_post


# ---------------------------------------------------------------------------
# voice clone
# ---------------------------------------------------------------------------


def test_clone_saves_profile_with_absolute_ref(fake_post, tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFF fake wav")

    result = runner.invoke(
        cli.app,
        [
            "voice",
            "clone",
            "--reference",
            str(ref),
            "--transcript",
            "This is what I said in the clip.",
            "--name",
            "My Clone",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = fake_post[0]["json"]
    assert payload["voice_id"] == "my-clone"
    assert payload["engine"] == "omnivoice"
    assert payload["settings"] == {
        "ref_audio": str(ref.resolve()),
        "ref_text": "This is what I said in the clip.",
    }
    assert "voice preview my-clone" in _flat(result.output)


def test_clone_missing_reference_file(fake_post, tmp_path):
    result = runner.invoke(
        cli.app,
        [
            "voice",
            "clone",
            "--reference",
            str(tmp_path / "nope.wav"),
            "--transcript",
            "hello",
            "--name",
            "Ghost",
        ],
    )
    assert result.exit_code == 1
    assert not fake_post


def test_clone_requires_transcript(fake_post, tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFF fake wav")
    result = runner.invoke(
        cli.app,
        ["voice", "clone", "--reference", str(ref), "--name", "No Transcript"],
    )
    assert result.exit_code != 0
    assert not fake_post


def test_clone_rejects_blank_transcript(fake_post, tmp_path):
    ref = tmp_path / "sample.wav"
    ref.write_bytes(b"RIFF fake wav")
    result = runner.invoke(
        cli.app,
        ["voice", "clone", "--reference", str(ref), "--transcript", "   ", "--name", "Blank"],
    )
    assert result.exit_code == 1
    assert not fake_post


# ---------------------------------------------------------------------------
# voice preview
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_profile_get(monkeypatch):
    """Serve a stored omnivoice profile over fake httpx.get."""
    profile = VoiceProfile(
        voice_id="aussie-agent",
        display_name="Aussie Agent",
        engine="omnivoice",
        settings={"instruct": "female, australian accent"},
    )

    def get(url, **kwargs):
        if url.endswith("/voices/profiles/aussie-agent"):
            return SimpleNamespace(status_code=200, json=lambda: profile.model_dump(mode="json"))
        return SimpleNamespace(status_code=404, json=lambda: {}, text="not found")

    monkeypatch.setattr(cli.httpx, "get", get)
    return profile


def test_preview_synthesizes_and_plays(monkeypatch, fake_profile_get):
    backend = FakeTTSBackend()
    played = []
    monkeypatch.setattr("agent_ptt.tts.get_backend", lambda engine: backend)
    monkeypatch.setattr(cli, "_play_audio_bytes", played.append)

    result = runner.invoke(cli.app, ["voice", "preview", "aussie-agent", "--text", "G'day!"])

    assert result.exit_code == 0, result.output
    text, profile = backend.calls[0]
    assert text == "G'day!"
    assert profile.settings == {"instruct": "female, australian accent"}
    assert played == [FAKE_AUDIO]


def test_preview_missing_profile(monkeypatch, fake_profile_get):
    result = runner.invoke(cli.app, ["voice", "preview", "nonexistent"])
    assert result.exit_code == 1


def test_preview_engine_not_installed(monkeypatch, fake_profile_get):
    def raise_unknown(engine):
        raise ValueError("Unknown TTS engine")

    monkeypatch.setattr("agent_ptt.tts.get_backend", raise_unknown)
    result = runner.invoke(cli.app, ["voice", "preview", "aussie-agent"])
    assert result.exit_code == 1
    assert "uv sync --extra omnivoice" in _flat(result.output)
