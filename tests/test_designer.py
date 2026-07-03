"""LLM voice designer — parsing robustness, fallback, pinning integration."""

import pytest

from agent_ptt.designer import LLMVoiceDesigner, parse_instruct
from agent_ptt.models import PinnedVoiceDB
from agent_ptt.voicedesign import (
    get_or_create_pinned_voice,
    hash_instruct,
    list_pinned_voices,
    redesign_pinned_voice,
)
from tests.test_api import _create_channel

# ---------------------------------------------------------------------------
# parse_instruct
# ---------------------------------------------------------------------------


def test_parse_clean_answer():
    raw = "female, young adult, british accent, high pitch"
    assert parse_instruct(raw, "Claude") == raw


def test_parse_messy_casing_and_punctuation():
    raw = 'Female, Young Adult, British Accent, High Pitch."'
    assert parse_instruct(raw, "Claude") == "female, young adult, british accent, high pitch"


def test_parse_partial_answer_fills_from_hash():
    result = parse_instruct("male, british accent", "Claude")
    fallback = dict(
        zip(
            ["gender", "age", "accent", "pitch"],
            hash_instruct("Claude").split(", "),
            strict=True,
        )
    )
    parts = result.split(", ")
    assert parts[0] == "male"
    assert parts[2] == "british accent"
    assert parts[1] == fallback["age"]
    assert parts[3] == fallback["pitch"]


def test_parse_garbage_falls_back_to_hash():
    assert parse_instruct("I cannot answer that question!", "Claude") == hash_instruct("Claude")


def test_parse_bare_category_words_are_completed():
    """Small LLMs often answer 'british' instead of 'british accent'."""
    result = parse_instruct("male, young adult, british, medium tone", "Claude")
    parts = result.split(", ")
    assert parts[0] == "male"
    assert parts[1] == "young adult"
    assert parts[2] == "british accent"


def test_parse_close_typos_are_matched():
    result = parse_instruct("femal, britsh accent", "Claude")
    assert result.startswith("female")
    assert "british accent" in result


def test_parse_never_produces_invalid_items():
    from agent_ptt.voicedesign import ACCENTS, AGES, GENDERS, PITCHES

    valid = set(GENDERS) | set(AGES) | set(ACCENTS) | set(PITCHES)
    for raw in ["", "male male male", "very british, extremely old", "x, y, z, w, v"]:
        parts = parse_instruct(raw, "SomeHandle").split(", ")
        assert len(parts) == 4
        assert all(p in valid for p in parts)


# ---------------------------------------------------------------------------
# LLMVoiceDesigner
# ---------------------------------------------------------------------------


def test_designer_uses_injected_generate():
    prompts = []

    def fake_generate(prompt):
        prompts.append(prompt)
        return "male, elderly, british accent, very low pitch"

    designer = LLMVoiceDesigner(generate_fn=fake_generate)
    instruct = designer.design_instruct("Professor Oak")

    assert instruct == "male, elderly, british accent, very low pitch"
    assert "Professor Oak" in prompts[0]


def test_designer_validates_sloppy_output():
    designer = LLMVoiceDesigner(generate_fn=lambda p: '"FEMALE!, Australian Accent... maybe?"')
    parts = designer.design_instruct("Sakura").split(", ")
    assert parts[0] == "female"
    assert parts[2] == "australian accent"


# ---------------------------------------------------------------------------
# Pinning integration
# ---------------------------------------------------------------------------


@pytest.fixture
def llm_designer(monkeypatch):
    """Make the LLM designer available with a fixed creative answer."""
    designer = LLMVoiceDesigner(generate_fn=lambda p: "male, elderly, british accent, low pitch")
    monkeypatch.setattr("agent_ptt.designer.designer_available", lambda: True)
    monkeypatch.setattr("agent_ptt.designer.get_designer", lambda: designer)
    return designer


def test_pin_uses_llm_for_omnivoice(db_session, llm_designer):
    profile = get_or_create_pinned_voice("Professor Oak", db_session, engine="omnivoice")
    assert profile.settings == {"instruct": "male, elderly, british accent, low pitch"}
    assert db_session.get(PinnedVoiceDB, "professor oak").source == "llm"


def test_pin_falls_back_to_hash_when_llm_fails(db_session, monkeypatch):
    monkeypatch.setattr("agent_ptt.designer.designer_available", lambda: True)

    def boom():
        raise RuntimeError("model exploded")

    monkeypatch.setattr("agent_ptt.designer.get_designer", boom)

    profile = get_or_create_pinned_voice("Claude", db_session, engine="omnivoice")
    assert profile.settings == {"instruct": hash_instruct("Claude")}
    assert db_session.get(PinnedVoiceDB, "claude").source == "hash"


def test_pin_ignores_llm_for_edge_tts(db_session, llm_designer):
    profile = get_or_create_pinned_voice("Claude", db_session, engine="edge-tts")
    assert profile.engine == "edge-tts"
    assert db_session.get(PinnedVoiceDB, "claude").source == "hash"


def test_redesign_replaces_pin(db_session, monkeypatch):
    first = get_or_create_pinned_voice("Claude", db_session, engine="omnivoice")

    designer = LLMVoiceDesigner(generate_fn=lambda p: "female, teenager, korean accent, high pitch")
    monkeypatch.setattr("agent_ptt.designer.designer_available", lambda: True)
    monkeypatch.setattr("agent_ptt.designer.get_designer", lambda: designer)

    redesigned = redesign_pinned_voice("Claude", db_session, engine="omnivoice")
    assert redesigned.settings != first.settings
    assert redesigned.settings == {"instruct": "female, teenager, korean accent, high pitch"}

    # The pin now serves the new voice
    current = get_or_create_pinned_voice("Claude", db_session, engine="omnivoice")
    assert current.settings == redesigned.settings
    assert db_session.get(PinnedVoiceDB, "claude").source == "llm"


def test_list_pinned_voices(db_session):
    get_or_create_pinned_voice("Alpha", db_session)
    get_or_create_pinned_voice("Beta", db_session)

    pins = list_pinned_voices(db_session)
    assert {p["handle"] for p in pins} == {"alpha", "beta"}
    assert all(p["source"] == "hash" and p["settings"] for p in pins)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


def test_api_pinned_and_redesign(client, db_session):
    channel_id = _create_channel(client)
    client.post(f"/channels/{channel_id}/join", json={"handle": "Claude"})

    pins = client.get("/voices/pinned").json()
    assert [p["handle"] for p in pins] == ["claude"]

    redesigned = client.post("/voices/pinned/Claude/redesign").json()
    assert redesigned["voice_id"] == "auto-claude"

    pins = client.get("/voices/pinned").json()
    assert len(pins) == 1
