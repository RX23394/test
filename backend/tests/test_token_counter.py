"""Tests for tiktoken-first token counting."""

import pytest
import tiktoken

from app.services import token_counter as token_counter_module
from app.services.token_counter import TokenCounter


def test_token_counter_uses_tiktoken_when_available() -> None:
    """Installed tiktoken provides the exact encoding token count."""
    text = "OSPF routing with IPv6"
    expected = len(tiktoken.get_encoding("cl100k_base").encode(text))

    assert TokenCounter().count(text) == expected


def test_token_counter_returns_zero_for_empty_text() -> None:
    """Empty text always has a zero token count."""
    assert TokenCounter().count("") == 0


def test_token_counter_falls_back_to_character_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing tiktoken falls back to the Python character length."""
    text = "\u7f51\u7edc\u914d\u7f6e abc"
    monkeypatch.setattr(
        token_counter_module,
        "_load_tiktoken_encoding",
        lambda encoding_name: None,
    )

    assert TokenCounter().count(text) == len(text)
