"""Tests for auth module."""
from src.auth import AuthService, User


def test_register():
    service = AuthService()
    user = service.register("testuser", "test@example.com", "password123")
    assert user.username == "testuser"
    assert user.email == "test@example.com"


def test_login_success():
    service = AuthService()
    service.register("testuser", "test@example.com", "password123")
    token = service.login("testuser", "password123")
    assert token is not None


def test_login_failure():
    service = AuthService()
    token = service.login("nonexistent", "password")
    assert token is None
