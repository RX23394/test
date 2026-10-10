"""Conversational retrieval query construction."""

from collections.abc import Sequence
from typing import Protocol

DEFAULT_HISTORY_TURNS = 3


class HistoryMessage(Protocol):
    """Message fields required to build a follow-up retrieval query."""

    role: str
    content: str


def build_retrieval_query(
    question: str,
    history: Sequence[HistoryMessage] = (),
    *,
    turns: int = DEFAULT_HISTORY_TURNS,
) -> str:
    """Combine the current question with the most recent user turns.

    A follow-up such as "那它的缺点呢？" carries no retrievable terms on its own, so
    the preceding questions are prepended to the embedding query. Assistant
    answers are deliberately skipped: they are long, and mixing them into one
    query vector dilutes the topic the user is asking about.
    """
    normalized_question = question.strip()
    if not normalized_question:
        raise ValueError("question must not be empty")
    if turns <= 0:
        return normalized_question
    previous_questions = [
        message.content.strip()
        for message in history
        if message.role == "user" and message.content.strip()
    ][-turns:]
    return "\n".join([*previous_questions, normalized_question])
