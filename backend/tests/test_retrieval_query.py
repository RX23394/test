"""Tests for conversational follow-up retrieval queries."""

from dataclasses import dataclass

import pytest

from app.services.retrieval_query import DEFAULT_HISTORY_TURNS, build_retrieval_query


@dataclass(frozen=True)
class HistoryTurn:
    """One replayed conversation message."""

    role: str
    content: str


def test_retrieval_query_without_history_is_the_question() -> None:
    """A first question is embedded exactly as asked."""
    assert build_retrieval_query("  What is OSPF?  ") == "What is OSPF?"


def test_retrieval_query_prepends_previous_user_questions() -> None:
    """A follow-up carries the topics of the questions before it."""
    history = [
        HistoryTurn(role="user", content="What is OSPF?"),
        HistoryTurn(role="assistant", content="OSPF is a link-state protocol."),
        HistoryTurn(role="user", content="Which area types exist?"),
        HistoryTurn(role="assistant", content="Backbone, stub, and NSSA."),
    ]

    query = build_retrieval_query("那它的缺点呢？", history)

    assert query == "What is OSPF?\nWhich area types exist?\n那它的缺点呢？"


def test_retrieval_query_skips_answers_and_keeps_the_newest_turns() -> None:
    """Answers are excluded and only the configured number of turns is used."""
    history = [
        HistoryTurn(role="user", content="first"),
        HistoryTurn(role="assistant", content="answer one"),
        HistoryTurn(role="user", content="second"),
        HistoryTurn(role="assistant", content="answer two"),
        HistoryTurn(role="user", content="third"),
        HistoryTurn(role="assistant", content="answer three"),
        HistoryTurn(role="user", content="fourth"),
    ]

    query = build_retrieval_query("follow-up", history)

    assert DEFAULT_HISTORY_TURNS == 3
    assert query == "second\nthird\nfourth\nfollow-up"


def test_retrieval_query_without_turns_uses_only_the_question() -> None:
    """History can be switched off without changing the current question."""
    history = [HistoryTurn(role="user", content="What is OSPF?")]

    assert build_retrieval_query("And BGP?", history, turns=0) == "And BGP?"


def test_retrieval_query_ignores_blank_history_entries() -> None:
    """Empty stored messages never add blank query lines."""
    history = [
        HistoryTurn(role="user", content="   "),
        HistoryTurn(role="user", content="What is OSPF?"),
    ]

    assert build_retrieval_query("And BGP?", history) == "What is OSPF?\nAnd BGP?"


def test_retrieval_query_rejects_a_blank_question() -> None:
    """An empty question is rejected before embedding."""
    with pytest.raises(ValueError, match="question must not be empty"):
        build_retrieval_query("   ", [HistoryTurn(role="user", content="prior")])
