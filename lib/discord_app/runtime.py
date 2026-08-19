from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lib.discord_app.hcaptcha_service import HCaptchaService
    from lib.discord_app.storage import ControlStore
    from lib.discord_app.supabase_service import SupabaseService
    from lib.discord_app.mail_config import GmailConfigService
    from lib.discord_app.cloudinary_service import CloudinaryService
    from lib.discord_app.session_authority import SessionAuthority


@dataclass(frozen=True, slots=True)
class RuntimeServices:
    """Explicit runtime dependency container.

    It mirrors the repository/adapter indirection used by the reviewed Elixir
    project while keeping the current Flask application behavior unchanged.
    Tests or future services can replace a dependency without importing a
    process-global implementation directly.
    """

    store: "ControlStore"
    provider: "SupabaseService"
    captcha: "HCaptchaService"
    gmail: "GmailConfigService"
    cloudinary: "CloudinaryService"
    session_authority: "SessionAuthority"
