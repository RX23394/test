"""FastAPI dependency for the parser registry."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.services.document_parser.docx import DocxParser
from app.services.document_parser.markdown import MarkdownParser
from app.services.document_parser.pdf import PDFParser
from app.services.document_parser.registry import ParserRegistry
from app.services.document_parser.txt import TxtParser


@lru_cache
def get_parser_registry() -> ParserRegistry:
    """Return the process-wide parser registry with supported parsers."""
    registry = ParserRegistry()
    registry.register(".docx", DocxParser())
    registry.register(".md", MarkdownParser())
    registry.register(".markdown", MarkdownParser())
    registry.register(".pdf", PDFParser())
    registry.register(".txt", TxtParser())
    return registry


ParserRegistryDependency = Annotated[ParserRegistry, Depends(get_parser_registry)]
