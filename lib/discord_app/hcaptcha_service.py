from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .storage import ControlStore


SITEKEY_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
SECRET_RE = re.compile(r"^ES_[A-Za-z0-9_-]{20,4093}$")
VERIFY_URL = "https://api.hcaptcha.com/siteverify"


class HCaptchaError(RuntimeError):
    def __init__(self, public_message: str, code: str = "captcha_error", internal: str = ""):
        super().__init__(public_message)
        self.public_message = public_message
        self.code = code
        self.internal = internal


@dataclass(frozen=True)
class HCaptchaResult:
    success: bool
    hostname: str
    error_codes: tuple[str, ...]


class HCaptchaService:
    """Server-side hCaptcha configuration and verification.

    The sitekey is intentionally public. The siteverify secret is retrieved only
    from the encrypted local control store (or one-time bootstrap environment)
    and is never returned to the browser.
    """

    def __init__(self, store: "ControlStore"):
        self.store = store
        self._env_sitekey = os.getenv("HCAPTCHA_SITE_KEY", "").strip()
        self._env_secret = os.getenv("HCAPTCHA_SECRET", "").strip()

    @property
    def sitekey(self) -> str:
        return (self.store.get_secret("HCAPTCHA_SITE_KEY") or self._env_sitekey).strip()

    @property
    def secret(self) -> str:
        return (self.store.get_secret("HCAPTCHA_SECRET") or self._env_secret).strip()

    @property
    def configured(self) -> bool:
        return bool(SITEKEY_RE.fullmatch(self.sitekey) and SECRET_RE.fullmatch(self.secret))

    @staticmethod
    def validate_sitekey(value: str) -> str:
        value = (value or "").strip()
        if not SITEKEY_RE.fullmatch(value):
            raise ValueError("Sitekey hCaptcha inválida.")
        return value

    @staticmethod
    def validate_secret(value: str) -> str:
        value = (value or "").strip()
        if not SECRET_RE.fullmatch(value):
            raise ValueError("Secret hCaptcha inválido.")
        return value

    def verify(self, token: str, remote_ip: str | None = None, timeout: int = 8) -> HCaptchaResult:
        if not self.configured:
            raise HCaptchaError("Verificação humana indisponível.", "not_configured")
        token = (token or "").strip()
        if not token or len(token) > 8192:
            raise HCaptchaError("Confirmação humana necessária.", "missing_or_invalid_token")

        payload: dict[str, str] = {
            "secret": self.secret,
            "response": token,
            "sitekey": self.sitekey,
        }
        if remote_ip:
            payload["remoteip"] = remote_ip

        body = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            VERIFY_URL,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "local-auth-hcaptcha/1.0",
            },
        )
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read(64 * 1024)
        except urllib.error.HTTPError as exc:
            raise HCaptchaError("Não foi possível validar a confirmação humana.", f"http_{exc.code}") from exc
        except Exception as exc:
            raise HCaptchaError("Não foi possível validar a confirmação humana.", exc.__class__.__name__) from exc

        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise HCaptchaError("Resposta inválida do serviço de verificação humana.", "invalid_response") from exc

        errors_raw = data.get("error-codes") or []
        if isinstance(errors_raw, str):
            errors = (errors_raw,)
        else:
            errors = tuple(str(item) for item in errors_raw if item)
        # Treat the hCaptcha siteverify decision as authoritative.  The returned
        # hostname is retained only for audit/diagnostics.  The application has
        # its own strict Host allowlist (APP_HOSTNAME=discord), while hCaptcha's
        # provider-side domain policy remains responsible for token/domain
        # acceptance.  Do not turn a provider success into a local false negative
        # based only on an optional/informational hostname field.
        success = bool(data.get("success"))
        hostname = str(data.get("hostname") or "")
        return HCaptchaResult(
            success=success,
            hostname=hostname,
            error_codes=errors,
        )
