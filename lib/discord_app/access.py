from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Actor:
    """Principal resolved exclusively from trusted server-side session state.

    Browser payloads never choose role or authority. The actor is deliberately
    small: identity, role and authentication authority are enough for the
    current login/register/admin control plane.
    """

    id: str
    role: str
    authenticated: bool
    authority: str

    @classmethod
    def anonymous(cls) -> "Actor":
        return cls(id="anonymous", role="anonymous", authenticated=False, authority="none")

    @classmethod
    def from_browser_session(cls, row: Any) -> "Actor":
        if not row:
            return cls.anonymous()
        try:
            user_id = str(row["user_id"] or "").strip()
            role = str(row["role"] or "user").strip().lower()
        except (KeyError, TypeError, IndexError):
            return cls.anonymous()
        if not user_id:
            return cls.anonymous()
        if role == "admin" and user_id.startswith("local-admin:"):
            return cls(id=user_id, role="admin", authenticated=True, authority="local-control")
        if role == "pending":
            return cls(id=user_id, role="pending", authenticated=True, authority="supabase-auth-pending")
        if role == "user":
            return cls(id=user_id, role="user", authenticated=True, authority="supabase-auth")
        return cls.anonymous()


class Policy:
    """Closed permission catalog; unknown roles/actions fail closed."""

    _ROLE_PERMISSIONS = {
        "anonymous": frozenset({"auth.begin"}),
        "pending": frozenset({"session.read", "session.logout", "shell.read", "email.resend", "email.verify.refresh", "email.change", "friend.request.create", "friend.request.read", "friend.request.cancel", "friend.request.accept", "friend.request.ignore", "guild.create", "guild.read", "voice.connect"}),
        "user": frozenset({"session.read", "session.logout", "shell.read", "friend.request.create", "friend.request.read", "friend.request.cancel", "friend.request.accept", "friend.request.ignore", "guild.create", "guild.read", "voice.connect"}),
        "admin": frozenset({"session.read", "session.logout", "admin.access", "admin.write"}),
    }

    @classmethod
    def allowed(cls, actor: Actor, permission: str) -> bool:
        if not isinstance(actor, Actor) or not isinstance(permission, str):
            return False
        return permission in cls._ROLE_PERMISSIONS.get(actor.role, frozenset())

    @classmethod
    def authorize(cls, actor: Actor, permission: str) -> None:
        if not cls.allowed(actor, permission):
            raise PermissionError(permission)
