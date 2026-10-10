"""Application service package."""

from app.services.auth import AuthService
from app.services.citation_resolver import (
    Citation,
    CitationResolutionError,
    CitationResolver,
)
from app.services.conversation import (
    ConversationDetail,
    ConversationNotFoundError,
    ConversationService,
)
from app.services.keyword_search import KeywordSearchResult, KeywordSearchService
from app.services.llm_errors import (
    LLMAPIError,
    LLMServiceError,
    LLMTimeoutError,
    LLMTokenLimitError,
)
from app.services.llm_provider import (
    LLMProvider,
    LLMProviderResponseError,
)
from app.services.prompt_builder import PromptBuilder
from app.services.rrf import RRFResult, RRFService, RRFSourceScore
from app.services.search import SearchService, SearchServiceResult
from app.services.vector_search import VectorSearchResult, VectorSearchService

__all__ = [
    "AuthService",
    "Citation",
    "CitationResolutionError",
    "CitationResolver",
    "ConversationDetail",
    "ConversationNotFoundError",
    "ConversationService",
    "KeywordSearchResult",
    "KeywordSearchService",
    "LLMAPIError",
    "LLMServiceError",
    "LLMTimeoutError",
    "LLMTokenLimitError",
    "LLMProvider",
    "LLMProviderResponseError",
    "PromptBuilder",
    "RRFResult",
    "RRFService",
    "RRFSourceScore",
    "SearchService",
    "SearchServiceResult",
    "VectorSearchResult",
    "VectorSearchService",
]
