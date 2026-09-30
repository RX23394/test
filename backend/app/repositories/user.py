"""User repository."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Persist and query users through a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self._session = session

    def get_by_id(self, user_id: int) -> User | None:
        """Return a user by primary key."""
        return self._session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        """Return a user by username."""
        statement = select(User).where(User.username == username)
        return self._session.scalar(statement)

    def list_all(self) -> Sequence[User]:
        """Return all users ordered by newest account first."""
        statement = select(User).order_by(User.created_at.desc(), User.id.desc())
        return self._session.scalars(statement).all()

    def create(
        self,
        *,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        """Create and persist a user."""
        user = User(
            username=username,
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=is_active,
        )
        self._session.add(user)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise
        self._session.refresh(user)
        return user

    def update_active(self, user: User, is_active: bool) -> User:
        """Update whether a user may authenticate."""
        user.is_active = is_active
        return self._commit_update(user)

    def update_admin(self, user: User, is_admin: bool) -> User:
        """Update administrator privileges for a user."""
        user.is_admin = is_admin
        return self._commit_update(user)

    def _commit_update(self, user: User) -> User:
        """Commit and refresh a modified user instance."""
        try:
            self._session.commit()
            self._session.refresh(user)
        except SQLAlchemyError:
            self._session.rollback()
            raise
        return user
