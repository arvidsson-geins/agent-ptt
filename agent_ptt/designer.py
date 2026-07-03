"""LLM-powered voice designer — creative instructs matching a handle's vibe.

Optional: needs transformers + torch (`uv sync --extra voice-designer`,
also satisfied by the omnivoice extra). A small instruct model picks
voice attributes for a handle; output is validated against the model
vocabulary and any gap is filled from the deterministic hash design,
so a sloppy LLM answer can never produce an invalid instruct.
"""

from __future__ import annotations

import difflib
import importlib.util
import logging
import re
from collections.abc import Callable

from agent_ptt.voicedesign import ACCENTS, AGES, GENDERS, PITCHES, hash_instruct

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"

_CATEGORIES: dict[str, list[str]] = {
    "gender": GENDERS,
    "age": AGES,
    "accent": ACCENTS,
    "pitch": PITCHES,
}

_PROMPT = """You are a voice casting director. Given a character name, choose voice \
attributes that match the vibe of the name.

Choose exactly one value from each list:
- gender: male, female
- age: teenager, young adult, middle-aged, elderly
- accent: american, australian, british, canadian, chinese, indian, japanese, \
korean, portuguese, russian
- pitch: very low, low, moderate, high, very high

Answer with only the four choices on one line, formatted exactly like:
female, young adult, british accent, high pitch

Name: {handle}
Answer:"""


def designer_available() -> bool:
    """True when the optional LLM dependencies are installed."""
    return (
        importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
    )


def parse_instruct(raw: str, handle: str) -> str:
    """Turn a raw LLM answer into a valid instruct, filling gaps from the hash.

    Each comma/newline-separated fragment is fuzzy-matched against the
    vocabulary; categories the LLM missed (or garbled) fall back to the
    deterministic hash design for the handle.
    """
    fallback = dict(zip(_CATEGORIES, hash_instruct(handle).split(", "), strict=True))

    chosen: dict[str, str] = {}
    for part in re.split(r"[,\n;]", raw.lower()):
        part = part.strip(" .!?\"'`*-")
        if not part:
            continue
        for category, options in _CATEGORIES.items():
            if category in chosen:
                continue
            # Bare category words first: "british" -> "british accent"
            candidates = [part, f"{part} accent", f"{part} pitch"]
            if direct := next((c for c in candidates if c in options), None):
                chosen[category] = direct
                break
            # Word-boundary containment ("australian accent... maybe"),
            # preferring the longest option ("very low pitch" over "low pitch")
            contained = [o for o in options if re.search(rf"\b{re.escape(o)}\b", part)]
            if contained:
                chosen[category] = max(contained, key=len)
                break
            # Then fuzzy match for typos ("britsh accent")
            if match := difflib.get_close_matches(part, options, n=1, cutoff=0.8):
                chosen[category] = match[0]
                break

    return ", ".join(chosen.get(category, fallback[category]) for category in _CATEGORIES)


class LLMVoiceDesigner:
    """Small local LLM that designs a voice instruct for a handle."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        generate_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.model_id = model_id
        self._generate_fn = generate_fn
        self._pipe = None

    def _default_generate(self, prompt: str) -> str:
        """Run the prompt through a lazily-loaded transformers pipeline."""
        if self._pipe is None:
            from transformers import pipeline

            logger.info(f"Loading voice designer LLM {self.model_id}")
            self._pipe = pipeline(
                "text-generation",
                model=self.model_id,
                dtype="auto",
                device_map="auto",
            )
            logger.info("Voice designer LLM loaded")

        messages = [{"role": "user", "content": prompt}]
        result = self._pipe(messages, max_new_tokens=30, do_sample=True, temperature=0.7)
        reply = result[0]["generated_text"][-1]
        return reply["content"] if isinstance(reply, dict) else str(reply)

    def design_instruct(self, handle: str) -> str:
        """Design a validated instruct string for a handle."""
        generate = self._generate_fn or self._default_generate
        raw = generate(_PROMPT.format(handle=handle))
        instruct = parse_instruct(raw, handle)
        logger.info(f"Designed voice for [{handle}]: {instruct} (raw: {raw!r})")
        return instruct


_designer: LLMVoiceDesigner | None = None


def get_designer() -> LLMVoiceDesigner:
    """Module-level designer singleton (keeps the LLM loaded)."""
    global _designer
    if _designer is None:
        _designer = LLMVoiceDesigner()
    return _designer
