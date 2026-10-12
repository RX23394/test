"""Reproduce the chat stream 500 in-process and print the real traceback.

Why this exists
---------------
A 500 from ``POST /api/chat/stream`` is sent by Starlette's
``ServerErrorMiddleware`` on the raw ASGI ``send``, which bypasses
``CORSMiddleware``. In a browser that surfaces only as "Failed to fetch" with no
usable detail, so the cause is invisible from the address bar and the backend
window may scroll past it. This script drives the same request through the same
dependency graph and reports what actually raised.

It is read-only with respect to the application: it creates one throwaway user
and one throwaway conversation so a question can be sent, and deletes the
conversation again at the end. No document, index, or configuration is touched.

Usage (from the project root):

    .venv\\Scripts\\python.exe diagnose_chat_500.py

Run it from a normal terminal. Launching the backend from a confined agent or
sandbox shell can leave the process without a writable temporary directory, in
which case importing the encoder stack raises ``FileNotFoundError`` and the
first question returns 500 even though the code is fine.

Paste the whole output when reporting the problem.
"""

from __future__ import annotations

import logging
import os
import secrets
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import engine, get_session_factory  # noqa: E402

SEPARATOR = "=" * 72
CHAT_PATH = "/api/chat/stream"
DIAGNOSTIC_QUESTION = "OSPF 邻居关系是怎么建立的？"


class TracebackCollector(logging.Handler):
    """Capture the tracebacks the application logs for unhandled errors.

    With ``raise_server_exceptions=False`` the 500 is returned instead of being
    raised, so the exception never reaches this script. The application's
    ``unhandled_exception_handler`` still logs it, which is where the one piece
    of information worth having actually lives.
    """

    def __init__(self) -> None:
        """Initialise an empty record list."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Store one emitted record."""
        self.records.append(record)

    def print_tracebacks(self) -> None:
        """Print every captured record that carries exception information."""
        for record in self.records:
            print(f"\n  logged: {record.name} - {record.getMessage()}")
            if record.exc_info is not None:
                traceback.print_exception(*record.exc_info)


def report_environment() -> None:
    """Print the settings and schema the running backend would also read."""
    settings = get_settings()
    print(SEPARATOR)
    print("SETTINGS")
    print(f"  app_env           : {settings.app_env}")
    print(f"  database_url      : {settings.database_url}")
    print(f"  frontend_origin   : {settings.frontend_origin}")
    print(f"  cors_allow_origins: {settings.cors_allow_origins}")
    print(f"  qdrant_url        : {settings.qdrant_url}")
    print(f"  openai_base_url   : {settings.openai_base_url}")
    print(f"  openai_model      : {settings.openai_model}")
    print(f"  retrieval_min     : {settings.retrieval_min_score}")

    with engine.connect() as connection:
        databases = connection.execute(text("pragma database_list")).all()
        print(f"\n  resolved sqlite   : {databases}")
        revision = connection.execute(
            text("select version_num from alembic_version")
        ).scalar()
        print(f"  alembic revision  : {revision}")
        tables = [
            row[0]
            for row in connection.execute(
                text(
                    "select name from sqlite_master "
                    "where type in ('table','view') order by name"
                )
            )
        ]
        print(f"  tables ({len(tables)})      : {tables}")
        for table in ("users", "documents", "conversations", "messages"):
            info = f"pragma table_info({table})"
            columns = [row[1] for row in connection.execute(text(info))]
            print(f"  {table:<17} : {columns}")


def report_expected_revision() -> None:
    """Print the migration head the code expects, via Alembic's own resolver."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    script = ScriptDirectory.from_config(config)
    print(f"\n  alembic head      : {script.get_current_head()}")


def _report_tempdir(label: str) -> None:
    """Report whether a usable temporary directory exists, without aborting.

    The probe is informational here: the application no longer depends on it,
    and stopping early would hide the failure this script exists to find.
    """
    try:
        print(f"  {label}: {tempfile.gettempdir()}")
    except Exception as exc:  # noqa: BLE001 - the condition being reported
        print(f"  {label}: FAILED ({type(exc).__name__}: {exc})")


def report_embedding_runtime() -> int:
    """Load the embedding stack and report exactly what fails, if anything.

    This is the component the chat route resolves *before* any of its own error
    handling runs: ``EmbeddingService`` imports ``sentence_transformers``, which
    imports ``transformers``, which imports ``torch._dynamo`` -- and that module
    builds a cache directory at import time. A failure here therefore surfaces
    as a bare 500 with no application-level message.
    """
    print(f"\n{SEPARATOR}")
    print("EMBEDDING RUNTIME (resolved before the route body runs)")
    print(f"  TEMP              : {os.environ.get('TEMP')!r}")
    print(f"  TMP               : {os.environ.get('TMP')!r}")
    inductor_cache = os.environ.get("TORCHINDUCTOR_CACHE_DIR")
    print(f"  TORCHINDUCTOR_CACHE_DIR: {inductor_cache!r}")
    print(f"  HF_HOME           : {os.environ.get('HF_HOME')!r}")
    print(f"  HF_HUB_CACHE      : {os.environ.get('HF_HUB_CACHE')!r}")
    _report_tempdir("  tempfile.gettempdir() before setup")

    from app.services.embedding import (
        MODEL_NAME,
        EmbeddingService,
        embedding_cache_directory,
        ensure_embedding_caches,
    )

    # Apply the same cache redirection the application performs before importing
    # the encoder, so a broken system temporary directory cannot mask the error
    # this probe is actually looking for.
    print(f"  resolved cache    : {embedding_cache_directory()}")
    ensure_embedding_caches()
    print(f"  inductor cache    : {os.environ.get('TORCHINDUCTOR_CACHE_DIR')!r}")
    _report_tempdir("  tempfile.gettempdir() after setup ")

    try:
        import sentence_transformers  # noqa: F401

        print("  import sentence_transformers: ok")
    except Exception:  # noqa: BLE001 - report the real import failure
        print("  import sentence_transformers: FAILED")
        traceback.print_exc()
        return 1

    try:
        service = EmbeddingService()
        print(f"  EmbeddingService({MODEL_NAME}): constructed")
    except Exception:  # noqa: BLE001 - model missing / unloadable
        print("  EmbeddingService: FAILED (model could not be loaded)")
        traceback.print_exc()
        return 1

    try:
        vector = service.embed_query("diagnostic")
        print(f"  embed_query dimension: {len(vector[0])}")
    except Exception:  # noqa: BLE001 - encoder call failure
        print("  embed_query: FAILED")
        traceback.print_exc()
        return 1

    return 0


def report_retrieval_legs(query: str) -> int:
    """Exercise each retrieval dependency and report the failing one.

    ``HybridSearchService.search`` wraps every failure in ``HybridSearchError``
    and the route turns that into "Search service is unavailable", so the client
    never learns which of the three dependencies actually broke. Probing them
    individually is the only way to tell a stopped Qdrant from a database
    whose search index is missing.
    """
    print(f"\n{SEPARATOR}")
    print("RETRIEVAL DEPENDENCIES")
    settings = get_settings()
    print(f"  query             : {query}")
    print(f"  qdrant_url        : {settings.qdrant_url}")
    print(f"  collection        : {settings.qdrant_collection_name}")
    print(f"  retrieval_min     : {settings.retrieval_min_score}")

    print("\n  [1] Qdrant collection")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        exists = client.collection_exists(settings.qdrant_collection_name)
        print(f"      collection_exists: {exists}")
        if exists:
            info = client.get_collection(settings.qdrant_collection_name)
            print(f"      points_count     : {info.points_count}")
    except Exception:  # noqa: BLE001 - the condition being diagnosed
        print("      FAILED - the vector store is unreachable")
        traceback.print_exc()
        return 1

    print("\n  [2] Query embedding")
    try:
        from app.services.embedding import EmbeddingService

        vector = EmbeddingService().embed_query(query)[0]
        print(f"      dimension: {len(vector)}")
    except Exception:  # noqa: BLE001
        print("      FAILED")
        traceback.print_exc()
        return 1

    print("\n  [3] Vector leg")
    try:
        from app.rag.dependencies import get_qdrant_repository

        candidates = get_qdrant_repository().search(vector, 30)
        print(f"      candidates: {len(candidates)}")
    except Exception:  # noqa: BLE001
        print("      FAILED")
        traceback.print_exc()
        return 1

    print("\n  [4] Keyword leg (FTS5)")
    try:
        from app.db.session import SessionFactory
        from app.repositories.fts import FtsChunkRepository

        with SessionFactory() as session:
            stored = FtsChunkRepository(session).search(query, 20)
        print(f"      candidates: {len(stored)}")
    except Exception:  # noqa: BLE001
        print("      FAILED - the keyword index is missing or stale")
        traceback.print_exc()
        return 1

    print("\n  [5] Hybrid fusion")
    try:
        from app.rag.dependencies import get_embedding_service, get_qdrant_repository
        from app.db.session import SessionFactory
        from app.repositories.fts import FtsChunkRepository
        from app.services.search import HybridSearchService

        with SessionFactory() as session:
            service = HybridSearchService(
                embedding_provider=get_embedding_service(),
                vector_repository=get_qdrant_repository(),
                text_repository=FtsChunkRepository(session),
                min_vector_score=settings.retrieval_min_score,
            )
            results = service.search(query)
        print(f"      results: {len(results)}")
    except Exception:  # noqa: BLE001
        print("      FAILED - this is the cause of the 503")
        traceback.print_exc()
        return 1

    print("\n  all retrieval legs healthy")
    return 0


def exercise_chat() -> int:
    """Send one question and print the full exception when it fails."""
    from fastapi.testclient import TestClient

    from app.auth.security import hash_password
    from app.main import app
    from app.models.conversation import Conversation
    from app.models.user import User

    settings = get_settings()
    factory = get_session_factory()
    username = f"zz_diag_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(16)

    with factory() as session:
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_admin=False,
            is_active=True,
        )
        session.add(user)
        session.flush()
        conversation = Conversation(user_id=user.id, title="diagnostic")
        session.add(conversation)
        session.flush()
        user_id, conversation_id = user.id, conversation.id
        session.commit()

    print(f"\n{SEPARATOR}")
    print("REQUEST")
    print(f"  temporary user        : {username} (id {user_id})")
    print(f"  temporary conversation: id {conversation_id}")

    exit_code = 0
    # Attach the collector to the root logger so the application's own
    # "Unhandled error ..." record is captured whatever logger it uses.
    collector = TracebackCollector()
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.addHandler(collector)
    root_logger.setLevel(logging.INFO)
    try:
        # raise_server_exceptions=False is the point: it hands back the 500 the
        # browser would see, instead of re-raising inside this script.
        with TestClient(app, raise_server_exceptions=False) as client:
            login = client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            print(f"  login status          : {login.status_code}")

            payload = {
                "conversation_id": conversation_id,
                "message": DIAGNOSTIC_QUESTION,
            }
            response = client.post(
                CHAT_PATH,
                json=payload,
                headers={"Origin": settings.frontend_origin},
            )
            print(f"  chat status           : {response.status_code}")
            print(
                "  access-control-allow-origin: "
                f"{response.headers.get('access-control-allow-origin')!r}"
            )
            print(f"  body                  : {response.text[:400]!r}")
            if response.status_code != 200:
                exit_code = 1
    except Exception:  # noqa: BLE001 - the whole point is to show this
        print(f"\n{SEPARATOR}")
        print("CLIENT RAISED BEFORE READING A RESPONSE")
        traceback.print_exc()
        exit_code = 1
    finally:
        root_logger.removeHandler(collector)
        root_logger.setLevel(previous_level)
        print(f"\n{SEPARATOR}")
        print("APPLICATION TRACEBACKS")
        if collector.records:
            collector.print_tracebacks()
        else:
            print("  none logged during the request")
        with factory() as session:
            session.execute(
                text("delete from messages where conversation_id = :cid"),
                {"cid": conversation_id},
            )
            session.execute(
                text("delete from conversations where id = :cid"),
                {"cid": conversation_id},
            )
            session.execute(
                text("delete from users where id = :uid"),
                {"uid": user_id},
            )
            session.commit()
        print("\n  temporary rows removed")

    return exit_code


def main() -> int:
    """Report configuration, schema, and the outcome of one real question."""
    report_environment()
    report_expected_revision()

    # Probe the component the route resolves before its own error handling, so a
    # bare 500 is attributed to the real culprit instead of the route body.
    if report_embedding_runtime() != 0:
        print(f"\n{SEPARATOR}")
        print("STOPPED: the embedding runtime is broken, so /api/chat/stream")
        print("would return 500 before reaching any retrieval or LLM code.")
        return 1

    # Retrieval is the next layer; a failure there is reported to the client as
    # the generic "Search service is unavailable".
    if report_retrieval_legs(DIAGNOSTIC_QUESTION) != 0:
        print(f"\n{SEPARATOR}")
        print("STOPPED: retrieval is broken, so /api/chat/stream would answer")
        print("503 Search service is unavailable. See the failing leg above.")
        return 1

    print(f"\n{SEPARATOR}")
    print("SETTINGS LOADED - now driving one streaming request")
    try:
        return exercise_chat()
    except Exception:  # noqa: BLE001 - startup/dependency failure
        print(f"\n{SEPARATOR}")
        print("FAILED BEFORE THE REQUEST COULD BE SENT")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
