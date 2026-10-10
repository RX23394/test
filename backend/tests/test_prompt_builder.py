"""Tests for retrieval-grounded prompt message construction."""

from dataclasses import dataclass

import pytest

from app.services.prompt_builder import (
    DEFAULT_HISTORY_TOKEN_BUDGET,
    INSUFFICIENT_KNOWLEDGE_RESPONSE,
    PROMPT_CONTEXT_LIMIT,
    SYSTEM_PROMPT,
    PromptBuilder,
)
from app.services.search import SearchServiceResult


@dataclass(frozen=True)
class HistoryTurn:
    """One replayed conversation message."""

    role: str
    content: str


@dataclass(frozen=True)
class Source:
    """Citation source double accepted by PromptBuilder."""

    label: str
    document_id: int
    content: str
    page: int | None
    section: str | None


def create_source(label: str = "S1") -> Source:
    """Create one citation source for streaming prompt tests."""
    return Source(
        label=label,
        document_id=7,
        content="OSPF area design",
        page=12,
        section="Area",
    )


def create_chunk(index: int) -> SearchServiceResult:
    """Create one deterministic Top8 search chunk."""
    return SearchServiceResult(
        document=100 + index,
        page=index + 1,
        section=f"Section {index + 1}",
        chunk=f"Chunk content {index + 1}",
        score=1.0 / (61 + index),
    )


def test_prompt_builder_returns_system_and_user_messages() -> None:
    """Builder returns exactly one system and one user SDK message."""
    messages = PromptBuilder().build("What is OSPF?", [create_chunk(0)])

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert messages[1]["role"] == "user"


def test_system_prompt_contains_all_grounding_rules() -> None:
    """System instructions enforce sources, no invention, fallback, and labels."""
    messages = PromptBuilder().build("question", [])
    system_content = str(messages[0]["content"])

    assert "\u53ea\u80fd\u4f9d\u636e\u63d0\u4f9b\u7684\u8d44\u6599" in system_content
    assert "\u4e0d\u5141\u8bb8\u7f16\u9020" in system_content
    expected_fallback = (
        "\u5f53\u524d\u77e5\u8bc6\u5e93" "\u6ca1\u6709\u8db3\u591f\u8d44\u6599\u3002"
    )
    assert INSUFFICIENT_KNOWLEDGE_RESPONSE == expected_fallback
    assert INSUFFICIENT_KNOWLEDGE_RESPONSE in system_content
    assert "[S1]" in system_content
    assert "[S2]" in system_content


def test_user_prompt_contains_question_context_and_citations() -> None:
    """User content includes the question and numbered source blocks."""
    chunks = [create_chunk(0), create_chunk(1)]

    messages = PromptBuilder().build("  What is OSPF?  ", chunks)
    user_content = str(messages[1]["content"])

    assert user_content.startswith("Question:\nWhat is OSPF?")
    assert "\n\nContext:\n" in user_content
    assert "[S1]" in user_content
    assert "[S2]" in user_content
    assert "document: 100 | page: 1 | section: Section 1" in user_content
    assert "Chunk content 1" in user_content
    assert "document: 101 | page: 2 | section: Section 2" in user_content
    assert "Chunk content 2" in user_content


def test_prompt_builder_limits_context_to_top8() -> None:
    """Only the first eight ranked chunks receive citation labels."""
    chunks = [create_chunk(index) for index in range(10)]

    messages = PromptBuilder().build("question", chunks)
    user_content = str(messages[1]["content"])

    assert PROMPT_CONTEXT_LIMIT == 8
    assert "[S8]" in user_content
    assert "[S9]" not in user_content
    assert "Chunk content 8" in user_content
    assert "Chunk content 9" not in user_content


def test_prompt_builder_handles_empty_context() -> None:
    """No retrieved chunks produce an explicit empty-context marker."""
    messages = PromptBuilder().build("question", [])

    assert messages[1]["content"] == (
        "Question:\nquestion\n\nContext:\n\u65e0\u53ef\u7528\u8d44\u6599\u3002"
    )


def test_prompt_builder_omits_missing_page_and_section() -> None:
    """Unavailable source metadata is omitted without changing its label."""
    chunk = SearchServiceResult(
        document=7,
        page=None,
        section=None,
        chunk="Plain chunk",
        score=0.1,
    )

    messages = PromptBuilder().build("question", [chunk])
    user_content = str(messages[1]["content"])

    assert "[S1]\ndocument: 7\nPlain chunk" in user_content
    assert "page:" not in user_content
    assert "section:" not in user_content


def test_prompt_builder_rejects_blank_question() -> None:
    """A blank question is rejected before messages are constructed."""
    with pytest.raises(ValueError, match="question must not be empty"):
        PromptBuilder().build("  ", [create_chunk(0)])


def test_prompt_builder_replays_history_before_the_grounded_question() -> None:
    """Previous turns are injected as user and assistant messages in order."""
    history = [
        HistoryTurn(role="user", content="What is OSPF?"),
        HistoryTurn(role="assistant", content="A link-state routing protocol."),
    ]

    messages = PromptBuilder().build_from_sources(
        "那它的缺点呢？",
        [create_source()],
        history,
    )

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "What is OSPF?"
    assert messages[2]["content"] == "A link-state routing protocol."
    assert "那它的缺点呢？" in str(messages[3]["content"])
    assert "[S1]" in str(messages[3]["content"])


def test_prompt_builder_without_history_keeps_two_messages() -> None:
    """A first question is unaffected by the history feature."""
    messages = PromptBuilder().build_from_sources("What is OSPF?", [create_source()])

    assert [message["role"] for message in messages] == ["system", "user"]


def test_prompt_builder_drops_history_that_exceeds_the_token_budget() -> None:
    """Older turns are dropped first so the prompt stays inside its budget."""
    history = [
        HistoryTurn(role="user", content="old question " * 20),
        HistoryTurn(role="assistant", content="old answer"),
        HistoryTurn(role="user", content="newest question"),
    ]

    messages = PromptBuilder(history_token_budget=5).build_from_sources(
        "follow-up",
        [create_source()],
        history,
    )

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert messages[1]["content"] == "newest question"


def test_prompt_builder_trims_a_leading_answer_from_the_window() -> None:
    """A budget cut in the middle of an exchange never opens with a reply."""
    history = [
        HistoryTurn(role="user", content="What is OSPF?" * 10),
        HistoryTurn(role="assistant", content="A link-state protocol."),
        HistoryTurn(role="user", content="and BGP?"),
        HistoryTurn(role="assistant", content="A path-vector protocol."),
    ]

    messages = PromptBuilder(history_token_budget=15).build_from_sources(
        "compare them",
        [create_source()],
        history,
    )

    replay = messages[1:-1]
    assert replay
    assert replay[0]["role"] == "user"
    assert replay[-1]["role"] == "assistant"
    assert "and BGP?" == replay[0]["content"]


def test_prompt_builder_skips_unknown_history_roles_and_blank_content() -> None:
    """Unsupported roles and empty messages never reach the model."""
    history = [
        HistoryTurn(role="tool", content="tool output"),
        HistoryTurn(role="user", content="   "),
        HistoryTurn(role="user", content="real question"),
    ]

    messages = PromptBuilder().build_from_sources(
        "follow-up",
        [create_source()],
        history,
    )

    assert [message["content"] for message in messages[1:-1]] == ["real question"]


def test_prompt_builder_rejects_a_negative_history_budget() -> None:
    """A negative budget is a programming error, not a silent no-op."""
    with pytest.raises(ValueError, match="history_token_budget"):
        PromptBuilder(history_token_budget=-1)


def test_default_history_budget_is_five_hundred_twelve_tokens() -> None:
    """The documented default budget stays stable."""
    assert DEFAULT_HISTORY_TOKEN_BUDGET == 512
