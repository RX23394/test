"""Tests for the stateless retrieval-grounded ChatService workflow."""

from unittest.mock import Mock, call

import pytest

from app.services.chat_service import ChatResult, ChatService
from app.services.citation_builder import Citation, CitationBuilder
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import INSUFFICIENT_KNOWLEDGE_RESPONSE, PromptBuilder
from app.services.search import SearchService, SearchServiceResult


def create_chunk() -> SearchServiceResult:
    """Create one deterministic retrieved chunk."""
    return SearchServiceResult(
        document=7,
        page=12,
        section="Area",
        chunk="OSPF divides a network into areas.",
        score=0.1,
    )


def test_chat_service_runs_dependencies_in_required_order() -> None:
    """The workflow searches, prompts, generates, then builds citations."""
    workflow = Mock()
    search_service = Mock(spec=SearchService)
    prompt_builder = Mock(spec=PromptBuilder)
    llm_provider = Mock(spec=LLMProvider)
    citation_builder = Mock(spec=CitationBuilder)
    workflow.attach_mock(search_service, "search_service")
    workflow.attach_mock(prompt_builder, "prompt_builder")
    workflow.attach_mock(llm_provider, "llm_provider")
    workflow.attach_mock(citation_builder, "citation_builder")
    chunks = [create_chunk()]
    messages = [{"role": "user", "content": "grounded prompt"}]
    citations = [
        Citation(
            id="S1",
            document="7",
            page=12,
            section="Area",
            content="OSPF divides a network into areas.",
        )
    ]
    search_service.search.return_value = chunks
    prompt_builder.build.return_value = messages
    llm_provider.chat.return_value = "OSPF is link-state based [S1]."
    citation_builder.build.return_value = citations
    service = ChatService(
        search_service,
        prompt_builder,
        llm_provider,
        citation_builder,
    )

    result = service.chat("  What is OSPF?  ")

    assert result == ChatResult(
        answer="OSPF is link-state based [S1].",
        citations=citations,
    )
    assert workflow.mock_calls == [
        call.search_service.search("What is OSPF?"),
        call.prompt_builder.build("What is OSPF?", chunks),
        call.llm_provider.chat(messages),
        call.citation_builder.build(chunks),
    ]


def test_chat_service_integrates_prompt_and_citation_builders() -> None:
    """Real builders use the same Top8 chunks for prompt sources and output."""
    search_service = Mock(spec=SearchService)
    llm_provider = Mock(spec=LLMProvider)
    chunk = create_chunk()
    search_service.search.return_value = [chunk]
    llm_provider.chat.return_value = "Area information [S1]."
    service = ChatService(
        search_service,
        PromptBuilder(),
        llm_provider,
        CitationBuilder(),
    )

    result = service.chat("Explain areas")

    messages = llm_provider.chat.call_args.args[0]
    assert "[S1]" in str(messages[1]["content"])
    assert result.answer == "Area information [S1]."
    assert result.citations == [
        Citation(
            id="S1",
            document="7",
            page=12,
            section="Area",
            content="OSPF divides a network into areas.",
        )
    ]


def test_chat_service_rejects_blank_question_without_calling_dependencies() -> None:
    """Blank input is rejected before retrieval or generation begins."""
    search_service = Mock(spec=SearchService)
    prompt_builder = Mock(spec=PromptBuilder)
    llm_provider = Mock(spec=LLMProvider)
    citation_builder = Mock(spec=CitationBuilder)
    service = ChatService(
        search_service,
        prompt_builder,
        llm_provider,
        citation_builder,
    )

    with pytest.raises(ValueError, match="question must not be empty"):
        service.chat("   ")

    search_service.search.assert_not_called()
    prompt_builder.build.assert_not_called()
    llm_provider.chat.assert_not_called()
    citation_builder.build.assert_not_called()


def test_chat_service_does_not_build_citations_after_llm_failure() -> None:
    """A generation failure propagates and stops the remaining workflow."""
    search_service = Mock(spec=SearchService)
    prompt_builder = Mock(spec=PromptBuilder)
    llm_provider = Mock(spec=LLMProvider)
    citation_builder = Mock(spec=CitationBuilder)
    chunks = [create_chunk()]
    search_service.search.return_value = chunks
    prompt_builder.build.return_value = []
    llm_provider.chat.side_effect = RuntimeError("provider unavailable")
    service = ChatService(
        search_service,
        prompt_builder,
        llm_provider,
        citation_builder,
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.chat("What is OSPF?")

    citation_builder.build.assert_not_called()


def test_chat_service_returns_fallback_without_llm_when_search_is_empty() -> None:
    """Empty retrieval returns the fixed answer before prompt or model calls."""
    search_service = Mock(spec=SearchService)
    prompt_builder = Mock(spec=PromptBuilder)
    llm_provider = Mock(spec=LLMProvider)
    citation_builder = Mock(spec=CitationBuilder)
    search_service.search.return_value = []
    service = ChatService(
        search_service,
        prompt_builder,
        llm_provider,
        citation_builder,
    )

    result = service.chat("What is unknown?")

    assert result == ChatResult(
        answer=INSUFFICIENT_KNOWLEDGE_RESPONSE,
        citations=[],
    )
    prompt_builder.build.assert_not_called()
    llm_provider.chat.assert_not_called()
    citation_builder.build.assert_not_called()
