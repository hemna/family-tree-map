import secrets
from typing import Any


class SessionStore:
    def __init__(self, secret_key: str):
        self._secret_key = secret_key
        self._sessions: dict[str, dict[str, Any]] = {}

    def create(self) -> str:
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = {}
        return session_id

    def get(self, session_id: str) -> dict[str, Any] | None:
        return self._sessions.get(session_id)

    def set(self, session_id: str, key: str, value: Any) -> None:
        if session_id in self._sessions:
            self._sessions[session_id][key] = value

    def update(self, session_id: str, data: dict[str, Any]) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].update(data)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
