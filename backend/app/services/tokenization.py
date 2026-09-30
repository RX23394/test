"""Chinese-aware tokenization for the FTS5 keyword search path.

SQLite's built-in ``unicode61`` tokenizer treats a whole run of CJK characters
as a single token, so a Chinese query never matches Chinese content. Measured on
the previous schema, the paragraph "配置BGP邻居关系时，需要在对等体下指定对端自治
系统号" indexed as four multi-character tokens, and the queries ``bgp``,
``配置``, ``邻居`` and ``自治系统`` all returned zero rows.

Tokenizing with jieba at both index time and query time fixes that. Tokens are
stored space-separated in a dedicated column, so the FTS5 table itself stays on
the standard ``unicode61`` tokenizer and needs no per-connection registration.
"""

from dataclasses import dataclass, field

import jieba

# jieba is noisy on the command line: it prints its dictionary build to stderr.
jieba.setLogLevel(60)

DEFAULT_MAX_TOKEN_CHARS = 64

# Function words carry no retrieval signal, but they are emitted by jieba like
# any other word. Leaving them in an AND-joined query would require every chunk
# to contain words such as "是" or "的", which collapses recall.
STOPWORDS = frozenset(
    {
        # Chinese function words and interrogatives.
        "的",
        "了",
        "和",
        "与",
        "或",
        "是",
        "在",
        "有",
        "为",
        "对",
        "把",
        "被",
        "这",
        "那",
        "哪个",
        "哪些",
        "什么",
        "怎么",
        "怎样",
        "如何",
        "为什么",
        "哪",
        "吗",
        "呢",
        "吧",
        "啊",
        "请",
        "我",
        "你",
        "他",
        "它",
        "我们",
        "你们",
        "可以",
        "需要",
        "进行",
        "一个",
        "以及",
        "并且",
        "但是",
        "因为",
        "所以",
        "如果",
        "就是",
        "还是",
        "也是",
        "这个",
        "那个",
        # English function words.
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
    }
)


def is_searchable_token(token: str) -> bool:
    """Return whether a token can carry retrieval signal.

    Punctuation-only tokens such as "？" are dropped because they can never
    match indexed content, and an AND-joined query containing one would always
    return nothing.
    """
    if not any(character.isalnum() for character in token):
        return False
    return token.casefold() not in STOPWORDS


class TokenizationError(ValueError):
    """Raised when text cannot be tokenized for the search index."""


@dataclass(frozen=True, slots=True)
class TokenizerConfig:
    """Controls how source text becomes searchable tokens."""

    # ``cut_for_search`` also emits sub-words, which raises recall for compound
    # terms: "路由器" additionally yields "路由".
    search_mode: bool = True
    max_token_chars: int = DEFAULT_MAX_TOKEN_CHARS


@dataclass(frozen=True, slots=True)
class TokenizationService:
    """Turn source text into FTS5-safe tokens, identically at both ends.

    Index-time and query-time tokenization must agree exactly, so both paths go
    through this one service.
    """

    config: TokenizerConfig = field(default_factory=TokenizerConfig)

    def tokenize(self, text: str) -> list[str]:
        """Return searchable tokens for ``text`` in source order."""
        if not isinstance(text, str):
            raise TokenizationError("text must be a string")
        if not text.strip():
            return []

        segments = (
            jieba.cut_for_search(text) if self.config.search_mode else jieba.cut(text)
        )
        tokens: list[str] = []
        for segment in segments:
            token = segment.strip()
            if not token:
                continue
            if len(token) > self.config.max_token_chars:
                # A single runaway token would dominate BM25, so split it into
                # fixed windows instead of indexing it whole.
                tokens.extend(
                    token[index : index + self.config.max_token_chars]
                    for index in range(0, len(token), self.config.max_token_chars)
                )
                continue
            tokens.append(token)
        return tokens

    def tokenize_for_index(self, text: str) -> str:
        """Return the space-separated token column stored alongside content."""
        return " ".join(self.tokenize(text))

    def build_match_query(self, query: str) -> str:
        """Return an FTS5 MATCH expression, or an empty string when unusable.

        Tokens are quoted and combined with an explicit AND: the previous
        implementation combined them with OR, which let a long question match
        any chunk sharing one high-frequency word.

        Stopwords and punctuation are dropped before the AND is built, because
        requiring "是" in every matching chunk would collapse recall. When a
        query consists only of stopwords they are used anyway, so that asking
        "什么是" still searches rather than silently returning nothing.
        """
        tokens = self.tokenize(query)
        if not tokens:
            return ""
        searchable = [token for token in tokens if is_searchable_token(token)]
        selected = searchable or tokens

        unique_tokens: list[str] = []
        seen: set[str] = set()
        for token in selected:
            normalized = token.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique_tokens.append(token)
        return " AND ".join(
            f'"{token.replace(chr(34), chr(34) * 2)}"' for token in unique_tokens
        )


def get_tokenization_service() -> TokenizationService:
    """Return the process-wide tokenization service."""
    return TokenizationService()
