r"""Ask the chat pipeline one question and print the answer and its citations.

Runs the real request in-process, so it needs no running server. Useful for
checking retrieval quality on an arbitrary question without a browser.

Run from the project root:

    .venv\\Scripts\\python.exe scripts\\ask.py "你的问题"

Creates a throwaway user and conversation, sends the question through
``POST /api/chat/stream``, then removes the temporary rows.
"""

from __future__ import annotations

import json
import secrets
import sys
import traceback
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

from app.db.session import get_session_factory  # noqa: E402

QUESTION = sys.argv[1] if len(sys.argv) > 1 else "OSPF 邻居关系是怎么建立的？"


def main() -> int:
    """Stream one answer and report it without the surrounding noise."""
    from fastapi.testclient import TestClient

    from app.auth.security import hash_password
    from app.main import app
    from app.models.conversation import Conversation
    from app.models.user import User

    factory = get_session_factory()
    username = f"zz_ask_{secrets.token_hex(4)}"
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
        conversation = Conversation(user_id=user.id, title="ask")
        session.add(conversation)
        session.flush()
        user_id, conversation_id = user.id, conversation.id
        session.commit()

    answer: list[str] = []
    citations: list[dict] = []
    try:
        import logging

        logging.disable(logging.WARNING)
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            response = client.post(
                "/api/chat/stream",
                json={"conversation_id": conversation_id, "message": QUESTION},
            )
        for block in response.text.split("\n\n"):
            if not block.strip():
                continue
            event = "message"
            data = ""
            for line in block.splitlines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
            if not data:
                continue
            payload = json.loads(data)
            if event == "token":
                answer.append(payload.get("data", ""))
            elif event == "citation":
                citations = payload.get("data") or []
    except Exception:  # noqa: BLE001 - surface anything unexpected
        traceback.print_exc()
        return 1
    finally:
        with factory() as session:
            session.execute(
                text("delete from messages where conversation_id = :cid"),
                {"cid": conversation_id},
            )
            session.execute(
                text("delete from conversations where id = :cid"),
                {"cid": conversation_id},
            )
            session.execute(text("delete from users where id = :uid"), {"uid": user_id})
            session.commit()

    print(f"question: {QUESTION}")
    print(f"status  : {response.status_code}")
    print(f"\nanswer:\n{''.join(answer)}")
    if citations:
        print("\ncitations:")
        for citation in citations:
            print(f"  [{citation.get('id')}] {citation.get('document')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
