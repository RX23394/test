"""Chinese keyword search must actually match, on the real migrated schema.

The bug these tests cover: the FTS5 table used ``tokenize='unicode61'``, which
treats a whole run of CJK characters as one token. The paragraph
"配置BGP邻居关系时，需要在对等体下指定对端自治系统号" therefore indexed as four
multi-character tokens, and every realistic Chinese query returned zero rows, so
RRF silently degraded to vector-only retrieval.

These tests run against the schema produced by the migrations, not a hand-built
copy, so a future migration that changes the index shape cannot leave them
testing something the application no longer uses.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.document import DocumentRepository
from app.repositories.fts import FtsChunkRepository
from app.repositories.user import UserRepository
from app.schemas.chunk import Chunk
from app.services.search_index_rebuild import rebuild_document_chunks_index
from app.services.tokenization import (
    TokenizationService,
    is_searchable_token,
)
from tests.test_database_contract import upgrade_to_head

BGP_PARAGRAPH = (
    "配置BGP邻居关系时，需要在对等体下指定对端自治系统号。"
    "路由器之间建立会话后，会交换OPEN消息。"
)
OSPF_PARAGRAPH = (
    "OSPF路由器通过LSA交换链路状态信息，cost值影响选路结果。"
    "使用 show ip ospf neighbor 命令可以查看邻居状态。"
)


@pytest.fixture
def indexed_repository(tmp_path: Path) -> Iterator[FtsChunkRepository]:
    """Provide a repository whose table was created by the migrations."""
    database_path = tmp_path / "fts.db"
    upgrade_to_head(database_path)
    engine: Engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    with factory() as session:
        user = UserRepository(session).create(
            username="fts-owner",
            password_hash="hashed",
        )
        document = DocumentRepository(session).create(
            filename="stored.md",
            original_filename="guide.md",
            sha256="a" * 64,
            file_size=100,
            uploader_id=user.id,
        )
        repository = FtsChunkRepository(session)
        repository.replace_document_chunks(
            document,
            [
                Chunk(
                    content=BGP_PARAGRAPH,
                    page=1,
                    section="BGP",
                    chunk_index=0,
                ),
                Chunk(
                    content=OSPF_PARAGRAPH,
                    page=2,
                    section="OSPF",
                    chunk_index=1,
                ),
            ],
        )
        yield repository
    engine.dispose()


@pytest.mark.parametrize(
    "query",
    [
        "bgp",
        "BGP",
        "配置",
        "邻居",
        "自治系统",
        "BGP邻居",
        "配置BGP邻居关系",
    ],
)
def test_chinese_and_latin_terms_match_the_bgp_chunk(
    indexed_repository: FtsChunkRepository,
    query: str,
) -> None:
    """Every one of these queries returned nothing before the fix.

    "邻居" also appears in the OSPF paragraph, so only membership of the BGP
    chunk is asserted here; per-chunk isolation is covered separately below.
    """
    results = indexed_repository.search(query, limit=20)

    assert results, f"query {query!r} matched no chunk"
    assert 0 in {result.chunk_index for result in results}


@pytest.mark.parametrize("query", ["自治系统", "OPEN消息", "会话"])
def test_bgp_only_terms_do_not_match_the_ospf_chunk(
    indexed_repository: FtsChunkRepository,
    query: str,
) -> None:
    """Words unique to one chunk must not match the other."""
    results = indexed_repository.search(query, limit=20)

    assert results, f"query {query!r} matched no chunk"
    assert all(result.chunk_index == 0 for result in results)


@pytest.mark.parametrize("query", ["ospf", "OSPF", "链路状态", "cost", "show ip ospf"])
def test_ospf_terms_match_only_the_ospf_chunk(
    indexed_repository: FtsChunkRepository,
    query: str,
) -> None:
    """Terms must not leak across chunks."""
    results = indexed_repository.search(query, limit=20)

    assert results, f"query {query!r} matched no chunk"
    assert all(result.chunk_index == 1 for result in results)


def test_unrelated_query_returns_nothing(
    indexed_repository: FtsChunkRepository,
) -> None:
    """A query with no shared token must not match anything."""
    assert indexed_repository.search("烤面包的食谱", limit=20) == []


def test_search_returns_stored_content_not_tokens(
    indexed_repository: FtsChunkRepository,
) -> None:
    """The token column is an index detail and must not leak into results."""
    results = indexed_repository.search("BGP", limit=20)

    assert results[0].content == BGP_PARAGRAPH


def test_replace_removes_previous_rows(
    indexed_repository: FtsChunkRepository,
) -> None:
    """Re-indexing a document must drop its earlier keyword rows."""
    assert indexed_repository.search("配置", limit=20) != []
    assert indexed_repository.search("OSPF", limit=20) != []

    document_id = indexed_repository.list_stored_chunks()[0].document_id
    indexed_repository.delete_document(document_id)

    assert indexed_repository.search("配置", limit=20) == []
    assert indexed_repository.search("OSPF", limit=20) == []


def test_match_query_drops_function_words_and_punctuation() -> None:
    """AND-joining stopwords would require them in every matching chunk."""
    tokenizer = TokenizationService()

    assert tokenizer.build_match_query("什么是 OSPF？") == '"OSPF"'
    assert tokenizer.build_match_query("如何配置BGP邻居") == (
        '"配置" AND "BGP" AND "邻居"'
    )
    assert tokenizer.build_match_query("   ") == ""


def test_match_query_falls_back_when_everything_is_a_stopword() -> None:
    """A stopword-only query must still search instead of returning nothing."""
    tokenizer = TokenizationService()

    match_query = tokenizer.build_match_query("什么是")

    assert match_query != ""
    assert "什么" in match_query


def test_punctuation_only_tokens_are_not_searchable() -> None:
    """A punctuation token can never match indexed text."""
    assert is_searchable_token("？") is False
    assert is_searchable_token("，") is False
    assert is_searchable_token("BGP") is True
    assert is_searchable_token("802.1") is True


def test_latin_acronyms_survive_tokenization() -> None:
    """Network terms must stay intact as single tokens."""
    tokens = TokenizationService().tokenize("OSPF 与 BGP 的 cost 值")

    assert "OSPF" in tokens
    assert "BGP" in tokens
    assert "cost" in tokens


def test_rebuild_restores_tokenization_of_stored_chunks(tmp_path: Path) -> None:
    """A rebuild must re-tokenize stored content without touching sources."""
    database_path = tmp_path / "rebuild.db"
    upgrade_to_head(database_path)
    engine: Engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    factory: sessionmaker[Session] = sessionmaker(bind=engine)
    try:
        with factory() as session:
            user = UserRepository(session).create(
                username="rebuild-owner",
                password_hash="hashed",
            )
            document = DocumentRepository(session).create(
                filename="stored.md",
                original_filename="guide.md",
                sha256="b" * 64,
                file_size=100,
                uploader_id=user.id,
            )
            repository = FtsChunkRepository(session)
            repository.replace_document_chunks(
                document,
                [
                    Chunk(
                        content=BGP_PARAGRAPH,
                        page=1,
                        section="BGP",
                        chunk_index=0,
                    )
                ],
            )
            before = repository.list_stored_chunks()

            rebuilt = rebuild_document_chunks_index(session.connection())
            session.commit()

            assert rebuilt == len(before)
            assert repository.list_stored_chunks() == before
            assert repository.search("配置", limit=20) != []
    finally:
        engine.dispose()
