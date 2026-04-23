from __future__ import annotations

import os
from typing import Any, Mapping, MutableMapping

from supabase import Client, create_client


def init_auth_db(database_url: str | None = None) -> None:
    """Kept for compatibility; Supabase handles auth persistence."""
    _ = database_url


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def get_supabase_client() -> Client:
    url = _required_env("SUPABASE_URL")
    anon_key = _required_env("SUPABASE_ANON_KEY")
    return create_client(url, anon_key)


def _safe_get(mapping_or_obj: Any, key: str) -> Any:
    if isinstance(mapping_or_obj, Mapping):
        return mapping_or_obj.get(key)
    return getattr(mapping_or_obj, key, None)


def _extract_session_tokens(auth_response: Any) -> tuple[str | None, str | None]:
    session_obj = _safe_get(auth_response, "session")
    if session_obj is None:
        return None, None
    access_token = _safe_get(session_obj, "access_token")
    refresh_token = _safe_get(session_obj, "refresh_token")
    return access_token, refresh_token


def _extract_user(auth_response: Any) -> dict[str, str] | None:
    user_obj = _safe_get(auth_response, "user")
    if user_obj is None:
        return None
    user_id = _safe_get(user_obj, "id")
    email = _safe_get(user_obj, "email")
    if not isinstance(user_id, str) or not isinstance(email, str):
        return None
    return {"id": user_id, "email": email.lower()}


def _store_session(
    session_state: MutableMapping[str, Any],
    access_token: str | None,
    refresh_token: str | None,
    user: dict[str, str] | None,
) -> None:
    if not access_token or not refresh_token or not user:
        return
    session_state["access_token"] = access_token
    session_state["refresh_token"] = refresh_token
    session_state["user_id"] = user["id"]
    session_state["user_email"] = user["email"]


def register_user(email: str, password: str) -> tuple[bool, str]:
    normalized_email = email.strip().lower()
    if not normalized_email or "@" not in normalized_email:
        return False, "Please enter a valid email."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    try:
        client = get_supabase_client()
        response = client.auth.sign_up({"email": normalized_email, "password": password})
        user = _extract_user(response)
        if not user:
            return False, "Sign-up request submitted. Check email for verification."
        return True, "Account created. Please log in."
    except Exception as error:
        return False, f"Unable to create account: {error}"


def authenticate_user(
    email: str,
    password: str,
    session_state: MutableMapping[str, Any],
) -> tuple[bool, str]:
    normalized_email = email.strip().lower()
    try:
        client = get_supabase_client()
        response = client.auth.sign_in_with_password({"email": normalized_email, "password": password})
        access_token, refresh_token = _extract_session_tokens(response)
        user = _extract_user(response)
        if not access_token or not refresh_token or not user:
            return False, "Sign-in failed. Please verify your credentials."
        _store_session(session_state, access_token, refresh_token, user)
        return True, "Signed in."
    except Exception as error:
        return False, f"Unable to sign in: {error}"


def clear_auth_session(session_state: MutableMapping[str, Any]) -> None:
    for key in ("access_token", "refresh_token", "user_id", "user_email"):
        session_state.pop(key, None)


def get_authenticated_user(session_state: MutableMapping[str, Any]) -> dict[str, str] | None:
    access_token = session_state.get("access_token")
    user_id = session_state.get("user_id")
    user_email = session_state.get("user_email")
    if not access_token or not user_id or not user_email:
        return None

    try:
        client = get_supabase_client()
        auth_user = client.auth.get_user(access_token)
        user_obj = _safe_get(auth_user, "user")
        token_user_id = _safe_get(user_obj, "id")
        token_email = _safe_get(user_obj, "email")
        if token_user_id != user_id:
            clear_auth_session(session_state)
            return None
        if isinstance(token_email, str):
            session_state["user_email"] = token_email.lower()
        return {"id": str(user_id), "email": str(session_state["user_email"])}
    except Exception:
        clear_auth_session(session_state)
        return None
