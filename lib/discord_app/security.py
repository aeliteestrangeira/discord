from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet


LOCAL_ADDRS = {"127.0.0.1", "::1"}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token_hash(token: str) -> str:
    return sha256_text(token)


def new_token(bytes_len: int = 32) -> str:
    return secrets.token_urlsafe(bytes_len)


def constant_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def is_loopback(remote_addr: Optional[str]) -> bool:
    if not remote_addr:
        return False
    if remote_addr in LOCAL_ADDRS:
        return True
    try:
        return ipaddress.ip_address(remote_addr).is_loopback
    except ValueError:
        return False


def masked(value: str, keep_start: int = 14, keep_end: int = 6) -> str:
    value = value or ""
    if not value:
        return "não configurado"
    if len(value) <= keep_start + keep_end:
        return "•" * len(value)
    return f"{value[:keep_start]}{'•' * 12}{value[-keep_end:]}"


class KeyRing:
    def __init__(self, instance_dir: Path):
        self.instance_dir = instance_dir
        self.master_key_path = instance_dir / "master.key"
        self.csrf_key_path = instance_dir / "csrf.key"
        self.audit_key_path = instance_dir / "audit.key"
        self._ensure_keys()
        self.fernet = Fernet(self.master_key_path.read_bytes().strip())
        self.csrf_key = self.csrf_key_path.read_bytes()
        self.audit_key = self.audit_key_path.read_bytes()

    def _write_private(self, path: Path, data: bytes) -> None:
        path.write_bytes(data)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def _ensure_keys(self) -> None:
        self.instance_dir.mkdir(parents=True, exist_ok=True)
        if not self.master_key_path.exists():
            self._write_private(self.master_key_path, Fernet.generate_key())
        if not self.csrf_key_path.exists():
            self._write_private(self.csrf_key_path, secrets.token_bytes(32))
        if not self.audit_key_path.exists():
            self._write_private(self.audit_key_path, secrets.token_bytes(32))

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")

    def csrf_for_session(self, raw_session_token: str) -> str:
        return hmac.new(self.csrf_key, raw_session_token.encode("utf-8"), hashlib.sha256).hexdigest()

    def presence_for_session(self, raw_session_token: str) -> str:
        """Non-secret companion proof bound to one opaque server session.

        The HTTP-only session cookie remains the authentication credential. This
        second value is intentionally readable by same-origin JavaScript so the
        client can detect browser cookie removal immediately. Domain separation
        prevents the value from being reused as a CSRF token.
        """
        payload = b"session-presence\x00" + raw_session_token.encode("utf-8")
        return hmac.new(self.csrf_key, payload, hashlib.sha256).hexdigest()

    def audit_digest(self, payload: str) -> str:
        return hmac.new(self.audit_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
