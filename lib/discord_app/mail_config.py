from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .storage import ControlStore


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
GOOGLE_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{20,255}\.apps\.googleusercontent\.com$")
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


@dataclass(frozen=True, slots=True)
class GmailConfigSnapshot:
    sender_email: str
    client_id: str
    client_secret: str
    refresh_token: str

    @property
    def configured(self) -> bool:
        return bool(self.sender_email and self.client_id and self.client_secret and self.refresh_token)


class GmailConfigService:
    """Future Gmail API delivery configuration.

    v3.8 only stores/validates the OAuth material. Delivery remains Supabase Auth
    until a later mail adapter is deliberately enabled. Secrets stay in the
    encrypted local control store and are never echoed in clear text.
    """

    def __init__(self, store: ControlStore):
        self.store = store

    @property
    def sender_email(self) -> str:
        return (self.store.get_secret("GOOGLE_GMAIL_SENDER") or "").strip().lower()

    @property
    def client_id(self) -> str:
        return (self.store.get_secret("GOOGLE_GMAIL_CLIENT_ID") or "").strip()

    @property
    def client_secret(self) -> str:
        return (self.store.get_secret("GOOGLE_GMAIL_CLIENT_SECRET") or "").strip()

    @property
    def refresh_token(self) -> str:
        return (self.store.get_secret("GOOGLE_GMAIL_REFRESH_TOKEN") or "").strip()

    @property
    def configured(self) -> bool:
        return self.snapshot().configured

    @property
    def active_provider(self) -> str:
        # Explicitly fixed for this release. Gmail is configuration-only.
        return "supabase"

    def snapshot(self) -> GmailConfigSnapshot:
        return GmailConfigSnapshot(
            sender_email=self.sender_email,
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=self.refresh_token,
        )

    @staticmethod
    def validate_sender(value: str) -> str:
        value = (value or "").strip().lower()
        if len(value) > 320 or not EMAIL_RE.fullmatch(value):
            raise ValueError("E-mail remetente do Gmail inválido.")
        return value

    @staticmethod
    def validate_client_id(value: str) -> str:
        value = (value or "").strip()
        if not GOOGLE_CLIENT_ID_RE.fullmatch(value):
            raise ValueError("OAuth Client ID do Google inválido.")
        return value

    @staticmethod
    def validate_client_secret(value: str) -> str:
        value = (value or "").strip()
        if not (8 <= len(value) <= 4096):
            raise ValueError("OAuth Client Secret do Google inválido.")
        return value

    @staticmethod
    def validate_refresh_token(value: str) -> str:
        value = (value or "").strip()
        if not (20 <= len(value) <= 8192):
            raise ValueError("Refresh token do Google inválido.")
        return value

    def save_partial(
        self,
        *,
        admin_id: Optional[int],
        sender_email: str = "",
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
    ) -> list[str]:
        changed: list[str] = []
        if sender_email:
            self.store.set_secret("GOOGLE_GMAIL_SENDER", self.validate_sender(sender_email), admin_id)
            changed.append("GOOGLE_GMAIL_SENDER")
        if client_id:
            self.store.set_secret("GOOGLE_GMAIL_CLIENT_ID", self.validate_client_id(client_id), admin_id)
            changed.append("GOOGLE_GMAIL_CLIENT_ID")
        if client_secret:
            self.store.set_secret("GOOGLE_GMAIL_CLIENT_SECRET", self.validate_client_secret(client_secret), admin_id)
            changed.append("GOOGLE_GMAIL_CLIENT_SECRET")
        if refresh_token:
            self.store.set_secret("GOOGLE_GMAIL_REFRESH_TOKEN", self.validate_refresh_token(refresh_token), admin_id)
            changed.append("GOOGLE_GMAIL_REFRESH_TOKEN")
        return changed

    def clear(self) -> None:
        for name in (
            "GOOGLE_GMAIL_SENDER",
            "GOOGLE_GMAIL_CLIENT_ID",
            "GOOGLE_GMAIL_CLIENT_SECRET",
            "GOOGLE_GMAIL_REFRESH_TOKEN",
        ):
            self.store.delete_secret(name)
