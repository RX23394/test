"""User repository."""

from collections.abc import Sequence

from sqlalchemy import func, select
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

    def list_all(self, *, limit: int, offset: int = 0) -> Sequence[User]:
        """Return one page of users ordered by newest account first."""
        statement = (
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return self._session.scalars(statement).all()

    def count_all(self) -> int:
        """Return the total number of users, ignoring pagination."""
        return int(self._session.scalar(select(func.count()).select_from(User)) or 0)

    def create(
        self,
        *,
        username: str,
        password_hash: str,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        """Create a user inside the caller's transaction."""
        user = User(
            username=username,
            password_hash=password_hash,
            is_admin=is_admin,
            is_active=is_active,
        )
        self._session.add(user)
        self._session.flush()
        return user

    def update_active(self, user: User, is_active: bool) -> User:
        """Update whether a user may authenticate."""
        user.is_active = is_active
        return self._flush_update(user)

    def update_admin(self, user: User, is_admin: bool) -> User:
        """Update administrator privileges for a user."""
        user.is_admin = is_admin
        return self._flush_update(user)

    def bump_token_version(self, user: User) -> User:
        """Revoke every outstanding access token of a user.

        Called on logout and required by any future password change: the JWT
        itself cannot be withdrawn, so the generation it was minted with is what
        makes it stop working.
        """
        user.token_version += 1
        return self._flush_update(user)

    def _flush_update(self, user: User) -> User:
        """Write a modified user instance inside the caller's transaction."""
        self._session.flush()
        return user
