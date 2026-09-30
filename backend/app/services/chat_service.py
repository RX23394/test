"""Retrieval-grounded chat orchestration without persistence."""

from dataclasses import dataclass

from app.services.citation_builder import Citation, CitationBuilder
from app.services.llm_provider import LLMProvider
from app.services.prompt_builder import (
    INSUFFICIENT_KNOWLEDGE_RESPONSE,
    PromptBuilder,
)
from app.services.search import SearchService


@dataclass(frozen=True, slots=True)
class ChatResult:
    """One generated answer and its ordered retrieval citations."""

    answer: str
    citations: list[Citation]


class ChatService:
    """Orchestrate retrieval, prompting, generation, and citations."""

    def __init__(
        self,
        search_service: SearchService,
        prompt_builder: PromptBuilder,
        llm_provider: LLMProvider,
        citation_builder: CitationBuilder,
    ) -> None:
        """Initialize the stateless chat workflow dependencies."""
        self._search_service = search_service
        self._prompt_builder = prompt_builder
        self._llm_provider = llm_provider
        self._citation_builder = citation_builder

    def chat(self, question: str) -> ChatResult:
        """Return a grounded answer and citations for one question."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")

        chunks = self._search_service.search(normalized_question)
        if not chunks:
            return ChatResult(
                answer=INSUFFICIENT_KNOWLEDGE_RESPONSE,
                citations=[],
            )
        messages = self._prompt_builder.build(normalized_question, chunks)
        answer = self._llm_provider.chat(messages)
        citations = self._citation_builder.build(chunks)
        return ChatResult(answer=answer, citations=citations)
