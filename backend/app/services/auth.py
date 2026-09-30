"""Authentication service."""

from app.auth.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository

dummy_password_hash = hash_password("not-a-real-user-password")


class AuthService:
    """Coordinate user lookup and credential verification."""

    def __init__(self, repository: UserRepository) -> None:
        """Initialize the service with a user repository."""
        self._repository = repository

    def authenticate(self, username: str, password: str) -> User | None:
        """Return an active user when the supplied credentials are valid."""
        user = self._repository.get_by_username(username)
        if user is None:
            verify_password(password, dummy_password_hash)
            return None
        if not user.is_active or not verify_password(password, user.password_hash):
            return None
        return user
