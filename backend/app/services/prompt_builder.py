"""Retrieval-grounded chat message construction without model calls."""

from collections.abc import Sequence
from typing import Protocol, cast

from openai.types.chat import ChatCompletionMessageParam

from app.services.search import SearchServiceResult
from app.services.token_counter import TokenCounter

PROMPT_CONTEXT_LIMIT = 8
DEFAULT_HISTORY_TOKEN_BUDGET = 512
INSUFFICIENT_KNOWLEDGE_RESPONSE = (
    "\u5f53\u524d\u77e5\u8bc6\u5e93" "\u6ca1\u6709\u8db3\u591f\u8d44\u6599\u3002"
)
SYSTEM_PROMPT = (
    "\u4f60\u53ea\u80fd\u4f9d\u636e\u63d0\u4f9b"
    "\u7684\u8d44\u6599\u56de\u7b54\u95ee\u9898\u3002\n"
    "\u4e0d\u5141\u8bb8\u7f16\u9020\u3001\u731c\u6d4b"
    "\u6216\u8865\u5145\u8d44\u6599\u4e2d\u6ca1\u6709"
    "\u7684\u4fe1\u606f\u3002\n"
    "\u5982\u679c\u8d44\u6599\u4e0d\u8db3\u4ee5\u56de\u7b54\uff0c"
    "\u5fc5\u987b\u539f\u6837\u56de\u7b54\uff1a"
    f"{INSUFFICIENT_KNOWLEDGE_RESPONSE}\n"
    "\u5f15\u7528\u8d44\u6599\u65f6\u5fc5\u987b\u4f7f\u7528 "
    "[S1]\u3001[S2] \u8fd9\u6837\u7684\u7f16\u53f7\u683c\u5f0f\u3002"
)


class CitationPromptSource(Protocol):
    """Citation source fields required by streaming prompt construction."""

    label: str
    document_id: int
    content: str
    page: int | None
    section: str | None


class PromptHistoryMessage(Protocol):
    """Message fields required to replay previous conversation turns."""

    role: str
    content: str


class PromptBuilder:
    """Build grounded system and user messages from retrieved chunks."""

    def __init__(
        self,
        history_token_budget: int = DEFAULT_HISTORY_TOKEN_BUDGET,
    ) -> None:
        """Initialize the token budget available for replayed conversation turns."""
        if history_token_budget < 0:
            raise ValueError("history_token_budget must not be negative")
        self._history_token_budget = history_token_budget
        self._token_counter = TokenCounter()

    def build(
        self,
        question: str,
        chunks: Sequence[SearchServiceResult],
    ) -> list[ChatCompletionMessageParam]:
        """Return system and user messages without invoking a model."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        context = self._build_context(chunks[:PROMPT_CONTEXT_LIMIT])
        user_prompt = f"Question:\n{normalized_question}\n\n" f"Context:\n{context}"
        return cast(
            list[ChatCompletionMessageParam],
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

    def build_from_sources(
        self,
        question: str,
        sources: Sequence[CitationPromptSource],
        history: Sequence[PromptHistoryMessage] = (),
    ) -> list[ChatCompletionMessageParam]:
        """Build grounded messages, replaying recent turns within the budget."""
        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        blocks: list[str] = []
        for source in sources[:PROMPT_CONTEXT_LIMIT]:
            metadata = [f"document: {source.document_id}"]
            if source.page is not None:
                metadata.append(f"page: {source.page}")
            if source.section is not None:
                metadata.append(f"section: {source.section}")
            blocks.append(
                f"[{source.label}]\n" f"{' | '.join(metadata)}\n" f"{source.content}"
            )
        context = "\n\n".join(blocks) or "\u65e0\u53ef\u7528\u8d44\u6599\u3002"
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *self._build_history(history),
            {
                "role": "user",
                "content": (f"Question:\n{normalized_question}\n\nContext:\n{context}"),
            },
        ]
        return cast(list[ChatCompletionMessageParam], messages)

    def _build_history(
        self,
        history: Sequence[PromptHistoryMessage],
    ) -> list[dict[str, str]]:
        """Return the newest turns that fit the history token budget, in order.

        Walking backwards keeps the window contiguous and drops older turns
        first; a suffix that would start with an answer is trimmed so the replay
        never opens with a reply to a question the model cannot see.
        """
        selected: list[dict[str, str]] = []
        token_count = 0
        for message in reversed(list(history)):
            if message.role not in ("user", "assistant"):
                continue
            content = message.content.strip()
            if not content:
                continue
            message_tokens = self._token_counter.count(content)
            if token_count + message_tokens > self._history_token_budget:
                break
            selected.append({"role": message.role, "content": content})
            token_count += message_tokens
        selected.reverse()
        if selected and selected[0]["role"] == "assistant":
            selected.pop(0)
        return selected

    @staticmethod
    def _build_context(chunks: Sequence[SearchServiceResult]) -> str:
        """Format up to eight chunks with stable citation labels."""
        if not chunks:
            return "\u65e0\u53ef\u7528\u8d44\u6599\u3002"
        blocks: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = [f"document: {chunk.document}"]
            if chunk.page is not None:
                metadata.append(f"page: {chunk.page}")
            if chunk.section is not None:
                metadata.append(f"section: {chunk.section}")
            blocks.append(f"[S{index}]\n" f"{' | '.join(metadata)}\n" f"{chunk.chunk}")
        return "\n\n".join(blocks)
