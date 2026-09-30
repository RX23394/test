"""Create an administrator account interactively."""

import argparse
import getpass
import logging

from pydantic import ValidationError

from app.auth.security import hash_password
from app.core.logging import configure_logging
from app.db.session import SessionFactory
from app.repositories.user import UserRepository
from app.schemas.auth import UserCreate

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the administrator creation argument parser."""
    parser = argparse.ArgumentParser(description="Create a Network RAG administrator")
    parser.add_argument("--username", help="Administrator username")
    return parser


def main() -> None:
    """Prompt for credentials and create an administrator account."""
    configure_logging()
    arguments = build_parser().parse_args()
    username = arguments.username or input("Username: ").strip()
    password = getpass.getpass("Password: ")
    password_confirmation = getpass.getpass("Confirm password: ")

    if password != password_confirmation:
        logger.error("Passwords do not match")
        raise SystemExit(1)

    try:
        user_data = UserCreate(username=username, password=password)
    except ValidationError as exc:
        logger.error("Invalid administrator data: %s", exc)
        raise SystemExit(1) from exc

    with SessionFactory() as session:
        repository = UserRepository(session)
        if repository.get_by_username(user_data.username) is not None:
            logger.error("Username already exists: %s", user_data.username)
            raise SystemExit(1)
        user = repository.create(
            username=user_data.username,
            password_hash=hash_password(user_data.password),
            is_admin=True,
        )

    logger.info("Administrator created: %s (id=%s)", user.username, user.id)


if __name__ == "__main__":
    main()
