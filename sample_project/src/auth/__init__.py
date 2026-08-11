"""Auth module — login, registration, token management."""

import hashlib
import time
from typing import Optional


class User:
    """User model."""
    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email
        self._password_hash: str = ""


class AuthService:
    """Core authentication logic."""

    def __init__(self):
        self._users: dict[str, User] = {}
        self._sessions: dict[str, str] = {}
        # Rate limiting: track login attempts per username
        self._login_attempts: dict[str, list[float]] = {}
        self._max_attempts = 5
        self._lockout_duration = 300  # 5 minutes in seconds

    def register(self, username: str, email: str, password: str) -> User:
        """Register a new user."""
        user = User(username, email)
        user._password_hash = self._hash_password(password)
        self._users[username] = user
        return user

    def login(self, username: str, password: str) -> Optional[str]:
        """Authenticate and return a session token."""
        # Rate limiting check
        if self._is_rate_limited(username):
            return None

        user = self._users.get(username)
        if user is None:
            self._record_attempt(username)
            return None
        if user._password_hash != self._hash_password(password):
            self._record_attempt(username)
            return None
        # Successful login: clear attempts
        self._login_attempts.pop(username, None)
        token = self._generate_token(username)
        self._sessions[token] = username
        return token

    def _is_rate_limited(self, username: str) -> bool:
        """Check if the user is currently rate limited."""
        attempts = self._login_attempts.get(username, [])
        if not attempts:
            return False
        # Remove attempts older than lockout duration
        current_time = time.time()
        recent_attempts = [t for t in attempts if current_time - t < self._lockout_duration]
        self._login_attempts[username] = recent_attempts
        return len(recent_attempts) >= self._max_attempts

    def _record_attempt(self, username: str) -> None:
        """Record a login attempt for rate limiting."""
        if username not in self._login_attempts:
            self._login_attempts[username] = []
        self._login_attempts[username].append(time.time())

    def logout(self, token: str) -> bool:
        """Invalidate a session token."""
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    def validate_token(self, token: str) -> bool:
        """Check if a token is still valid."""
        return token in self._sessions

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def _generate_token(self, username: str) -> str:
        return hashlib.sha256(
            f"{username}:{time.time()}".encode()
        ).hexdigest()


class LoginController:
    """Handles login HTTP requests."""

    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    def handle_login(self, username: str, password: str) -> dict:
        """Process a login request."""
        token = self.auth_service.login(username, password)
        if token:
            return {"status": "ok", "token": token}
        return {"status": "error", "message": "Invalid credentials"}