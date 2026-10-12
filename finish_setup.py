"""One-shot setup after migrating the project database to head.

What it does
------------
1. Backs up both database files into .runtime/ first.
2. Copies the messages that only exist in the runtime copy (created while the
   backend was pointed at .runtime/network_rag.db) into the project database.
3. Refreshes the user rows whose session bookkeeping advanced in that copy.
4. Adds RETRIEVAL_MIN_SCORE=0.80 to .env when the line is missing, because the
   0.87 code default filters out every cross-language retrieval hit in this
   corpus. Pass --skip-env to leave .env untouched.

Every step is idempotent, so running it twice is harmless.

Usage (from the project root, in your own terminal - the DSH sandbox cannot
write to backend/):

    .venv\\Scripts\\python.exe finish_setup.py

Optional flags:

    --skip-env                do not touch .env
    --delete-runtime-copy     delete .runtime/network_rag.db after verifying
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_DB = ROOT / "backend" / "network_rag.db"
RUNTIME_DB = ROOT / ".runtime" / "network_rag.db"
ENV_FILE = ROOT / ".env"
RETRIEVAL_LINE = "RETRIEVAL_MIN_SCORE=0.80"


def read(path: Path, statement: str, params: tuple = ()) -> list[tuple]:
    """Run a read-only query against one database file."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return connection.execute(statement, params).fetchall()
    finally:
        connection.close()


def merge_databases() -> None:
    """Copy rows that exist only in the runtime copy into the project database."""
    if not PROJECT_DB.is_file():
        raise SystemExit(f"project database not found: {PROJECT_DB}")
    if not RUNTIME_DB.is_file():
        print("runtime copy not found - nothing to merge, skipping this step")
        return

    stamp = datetime.now().strftime("%H%M%S")
    # Both database files are named network_rag.db, so the backup name has to
    # come from an explicit label: deriving it from the file name made the two
    # backups collide and the second one overwrite the first.
    for label, source in (("project", PROJECT_DB), ("runtime", RUNTIME_DB)):
        backup = ROOT / ".runtime" / f"backup-{label}-{stamp}.db"
        shutil.copy2(source, backup)
        print(f"backup: {backup.name}")

    message_columns = [row[1] for row in read(RUNTIME_DB, "pragma table_info(messages)")]
    user_columns = [row[1] for row in read(RUNTIME_DB, "pragma table_info(users)")]

    existing_ids = {row[0] for row in read(PROJECT_DB, "select id from messages")}
    runtime_messages = read(
        RUNTIME_DB, f"select {', '.join(message_columns)} from messages order by id"
    )
    missing = [row for row in runtime_messages if row[0] not in existing_ids]
    print(f"messages to copy: {len(missing)} (ids {[row[0] for row in missing]})")

    runtime_users = {
        row[0]: row
        for row in read(RUNTIME_DB, f"select {', '.join(user_columns)} from users")
    }
    project_users = {
        row[0]: row
        for row in read(PROJECT_DB, f"select {', '.join(user_columns)} from users")
    }
    users_to_refresh = [
        user_id
        for user_id in sorted(project_users)
        if project_users[user_id] != runtime_users.get(user_id)
    ]
    print(f"users to refresh: {users_to_refresh}")

    connection = sqlite3.connect(PROJECT_DB, timeout=30)
    try:
        connection.execute("pragma foreign_keys = on")
        if missing:
            placeholders = ", ".join("?" for _ in message_columns)
            connection.executemany(
                f"insert into messages ({', '.join(message_columns)}) "
                f"values ({placeholders})",
                missing,
            )
        for user_id in users_to_refresh:
            assignments = ", ".join(
                f"{column} = ?" for column in user_columns if column != "id"
            )
            values = [
                runtime_users[user_id][index]
                for index, column in enumerate(user_columns)
                if column != "id"
            ]
            connection.execute(
                f"update users set {assignments} where id = ?", (*values, user_id)
            )
        connection.commit()
        if missing or users_to_refresh:
            print(
                f"merge committed: {len(missing)} message(s) inserted, "
                f"{len(users_to_refresh)} user row(s) refreshed"
            )
        else:
            print("nothing to copy - both databases already agree")
    finally:
        connection.close()

    print("\nverification:")
    for table in ("users", "documents", "conversations", "messages"):
        project_count = read(PROJECT_DB, f"select count(*) from {table}")[0][0]
        runtime_count = read(RUNTIME_DB, f"select count(*) from {table}")[0][0]
        flag = "OK" if project_count >= runtime_count else "MISMATCH"
        print(f"  {table:14} project={project_count:3} runtime={runtime_count:3}  {flag}")
    orphans = read(
        PROJECT_DB,
        "select count(*) from messages where conversation_id not in "
        "(select id from conversations)",
    )[0][0]
    print(f"  orphan messages = {orphans}")


def patch_env() -> None:
    """Ensure RETRIEVAL_MIN_SCORE is present so retrieval is not silently empty."""
    if not ENV_FILE.is_file():
        print(".env not found - skipping the retrieval floor step")
        return
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    if any(line.strip().startswith("RETRIEVAL_MIN_SCORE=") for line in lines):
        print("RETRIEVAL_MIN_SCORE already set in .env - leaving it alone")
        return
    lines.append(RETRIEVAL_LINE)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"added to .env: {RETRIEVAL_LINE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-env", action="store_true")
    parser.add_argument("--delete-runtime-copy", action="store_true")
    args = parser.parse_args()

    print("=== 1/2 merge runtime copy into the project database ===")
    merge_databases()

    print("\n=== 2/2 retrieval floor ===")
    if args.skip_env:
        print("skipped because of --skip-env")
    else:
        patch_env()

    if args.delete_runtime_copy:
        if RUNTIME_DB.is_file():
            RUNTIME_DB.unlink()
            print(f"\ndeleted {RUNTIME_DB} (a timestamped backup remains)")
    else:
        print(
            "\nthe runtime copy was kept; re-run with --delete-runtime-copy to "
            "remove it once you are satisfied"
        )

    print("\nrestart the backend afterwards so it reloads .env:")
    print("  start-dev.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
