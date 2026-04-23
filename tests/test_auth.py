from __future__ import annotations

from auth import clear_auth_session, get_authenticated_user


def test_clear_auth_session_removes_keys() -> None:
    session_state = {
        "access_token": "a",
        "refresh_token": "r",
        "user_id": "u",
        "user_email": "u@example.com",
    }
    clear_auth_session(session_state)
    assert "access_token" not in session_state
    assert "refresh_token" not in session_state
    assert "user_id" not in session_state
    assert "user_email" not in session_state


def test_get_authenticated_user_returns_none_without_tokens() -> None:
    session_state: dict[str, str] = {}
    assert get_authenticated_user(session_state) is None
