"""Fully mocked unit coverage for retrieval-grounded chat workflows."""

from collections.abc import Iterator
from unittest.mock import Mock

import pytest

from app.api.routes.chat import stream_chat_events
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.message import Message, MessageRole
from app.repositories.conversation import ConversationRepository
from app.repositories.document import DocumentRepository
from app.schemas.chat import CitationSource
from app.services import llm_provider as llm_provider_module
from app.services.chat_service import ChatResult, ChatService
from app.services.citation_builder import Citation, CitationBuilder
from app.services.citation_resolver import CitationResolver
from app.services.conversation import ConversationService
from app.services.keyword_search import KeywordSearchService
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import (
    INSUFFICIENT_KNOWLEDGE_RESPONSE,
    PromptBuilder,
)
from app.services.rrf import RRFResult, RRFService
from app.services.search import SearchService, SearchServiceResult
from app.services.vector_search import VectorSearchService


@pytest.fixture(autouse=True)
def forbid_real_openai(monkeypatch: pytest.MonkeyPatch) -> Iterator[Mock]:
    """Fail every test if it attempts to construct a real OpenAI client."""
    openai_constructor = Mock(side_effect=AssertionError("OpenAI is forbidden"))
    monkeypatch.setattr(llm_provider_module, "OpenAI", openai_constructor)
    yield openai_constructor
    openai_constructor.assert_not_called()


def create_search_chunk() -> SearchServiceResult:
    """Create one stable final retrieval result."""
    return SearchServiceResult(
        document=7,
        page=12,
        section="Area",
        chunk="OSPF divides a network into areas.",
        score=0.1,
    )


def create_citation() -> Citation:
    """Create one stable user-visible citation."""
    return Citation(
        id="S1",
        document="Cisco OSPF.pdf",
        page=12,
        section="Area",
        content="OSPF divides a network into areas.",
    )


def test_search_empty_uses_mock_retrievers_and_fusion() -> None:
    """Empty vector and keyword rankings produce an empty search result."""
    vector_search = Mock(spec=VectorSearchService)
    keyword_search = Mock(spec=KeywordSearchService)
    rrf = Mock(spec=RRFService)
    vector_search.search.return_value = []
    keyword_search.search.return_value = []
    rrf.fuse.return_value = []
    service = SearchService(vector_search, keyword_search, rrf)

    results = service.search("  unknown protocol  ")

    assert results == []
    vector_search.search.assert_called_once_with("unknown protocol")
    keyword_search.search.assert_called_once_with("unknown protocol")
    rrf.fuse.assert_called_once_with([], [])


def test_search_normal_uses_mock_retrievers_and_fusion() -> None:
    """A mocked fused result maps to the public SearchService result."""
    vector_search = Mock(spec=VectorSearchService)
    keyword_search = Mock(spec=KeywordSearchService)
    rrf = Mock(spec=RRFService)
    vector_candidate = Mock()
    keyword_candidate = Mock()
    vector_search.search.return_value = [vector_candidate]
    keyword_search.search.return_value = [keyword_candidate]
    rrf.fuse.return_value = [
        RRFResult(
            chunk="OSPF area content",
            document=7,
            page=12,
            section="Area",
            sources=(),
            final_score=0.03,
        )
    ]
    service = SearchService(vector_search, keyword_search, rrf)

    results = service.search("What is OSPF?")

    assert results == [
        SearchServiceResult(
            document=7,
            page=12,
            section="Area",
            chunk="OSPF area content",
            score=0.03,
        )
    ]
    rrf.fuse.assert_called_once_with([vector_candidate], [keyword_candidate])


def test_prompt_builder_formats_mock_chunk_with_source_label() -> None:
    """Prompt construction labels mocked retrieval metadata as S1."""
    chunk = Mock(spec=SearchServiceResult)
    chunk.document = 7
    chunk.page = 12
    chunk.section = "Area"
    chunk.chunk = "OSPF area content"

    messages = PromptBuilder().build("What is OSPF?", [chunk])

    assert messages[0]["role"] == "system"
    assert "[S1]" in str(messages[1]["content"])
    assert "page: 12" in str(messages[1]["content"])
    assert "section: Area" in str(messages[1]["content"])
    assert "OSPF area content" in str(messages[1]["content"])


def test_streaming_yields_mock_tokens_citation_and_done() -> None:
    """Streaming forwards separate mock deltas without buffering or OpenAI."""
    chat_provider = Mock(spec=LLMProvider)
    chat_provider.stream_chat.return_value = iter(["OSPF ", "answer [S1]."])
    source = CitationSource(
        label="S1",
        document_id=7,
        chunk_index=0,
        content="OSPF divides a network into areas.",
        page=12,
        section="Area",
    )
    citation = create_citation()

    events = list(
        stream_chat_events(
            "What is OSPF?",
            [source],
            [citation],
            chat_provider,
        )
    )

    assert [event.splitlines()[0] for event in events] == [
        "event: token",
        "event: token",
        "event: citation",
        "event: done",
    ]
    assert '"data":"OSPF "' in events[0]
    assert '"data":"answer [S1]."' in events[1]
    assert '"document":"Cisco OSPF.pdf"' in events[2]
    chat_provider.stream_chat.assert_called_once()
    messages = chat_provider.stream_chat.call_args.args[0]
    assert "[S1]" in str(messages)


def test_citation_resolves_mock_database_document() -> None:
    """Citation metadata comes from a mocked repository, not model output."""
    repository = Mock(spec=DocumentRepository)
    document = Mock(spec=Document)
    document.original_filename = "Cisco OSPF.pdf"
    result = Mock()
    result.document_id = 7
    result.page = 12
    result.section = "Area"
    result.content = "Original stored chunk"
    repository.get_by_ids.return_value = {7: document}

    citations = CitationResolver(repository).resolve([result])

    assert citations == [
        Citation(
            id="S1",
            document="Cisco OSPF.pdf",
            page=12,
            section="Area",
            content="Original stored chunk",
        )
    ]
    repository.get_by_ids.assert_called_once_with([7])


def test_chat_handles_mock_search_empty_and_normal_paths() -> None:
    """Chat skips the model for empty search and orchestrates normal search."""
    search = Mock(spec=SearchService)
    prompt = Mock(spec=PromptBuilder)
    llm = Mock(spec=LLMProvider)
    citation_builder = Mock(spec=CitationBuilder)
    service = ChatService(search, prompt, llm, citation_builder)
    search.search.return_value = []

    empty_result = service.chat("unknown")

    assert empty_result == ChatResult(
        answer=INSUFFICIENT_KNOWLEDGE_RESPONSE,
        citations=[],
    )
    prompt.build.assert_not_called()
    llm.chat.assert_not_called()

    chunk = create_search_chunk()
    citation = create_citation()
    messages = [{"role": "user", "content": "mock prompt"}]
    search.search.return_value = [chunk]
    prompt.build.return_value = messages
    llm.chat.return_value = "OSPF answer [S1]."
    citation_builder.build.return_value = [citation]

    normal_result = service.chat("What is OSPF?")

    assert normal_result == ChatResult(
        answer="OSPF answer [S1].",
        citations=[citation],
    )
    prompt.build.assert_called_once_with("What is OSPF?", [chunk])
    llm.chat.assert_called_once_with(messages)
    citation_builder.build.assert_called_once_with([chunk])


def test_conversation_create_query_message_and_delete_use_mock_repository() -> None:
    """Conversation lifecycle delegates every persistence action to a mock."""
    repository = Mock(spec=ConversationRepository)
    conversation = Mock(spec=Conversation)
    conversation.id = 11
    conversation.user_id = 3
    conversation.title = "OSPF"
    message = Mock(spec=Message)
    message.id = 21
    message.role = "user"
    message.content = "What is OSPF?"
    repository.create.return_value = conversation
    repository.get_for_user.return_value = conversation
    repository.list_for_user.return_value = [conversation]
    repository.list_messages.return_value = [message]
    repository.add_message.return_value = message
    service = ConversationService(repository)

    created = service.create(3, "  OSPF  ")
    conversations = service.list(3)
    saved_message = service.add_message(
        11,
        3,
        MessageRole.USER,
        "  What is OSPF?  ",
    )
    detail = service.get(11, 3)
    service.delete(11, 3)

    assert created is conversation
    assert conversations == [conversation]
    assert saved_message is message
    assert detail.conversation is conversation
    assert detail.messages == [message]
    repository.create.assert_called_once_with(user_id=3, title="OSPF")
    repository.add_message.assert_called_once_with(
        conversation_id=11,
        role=MessageRole.USER,
        content="What is OSPF?",
    )
    repository.list_messages.assert_called_once_with(11)
    repository.delete.assert_called_once_with(conversation)
