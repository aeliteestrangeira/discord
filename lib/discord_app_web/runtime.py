from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from lib.discord_app.bootstrap import migrate_bootstrap_env
from lib.discord_app.cloudinary_service import CloudinaryService
from lib.discord_app.hcaptcha_service import HCaptchaService
from lib.discord_app.mail_config import GmailConfigService, GMAIL_SEND_SCOPE
from lib.discord_app.paths import (
    PROJECT_ROOT as ROOT, CONFIG_DIR, ASSET_CSS_DIR, ASSET_JS_DIR, UI_JS_DIR,
    STATIC_PAGES_DIR, STATIC_FONTS_DIR, STATIC_ASSETS_DIR, STATIC_IMAGES_DIR,
    INSTANCE_DIR, RUNTIME_DIR,
)
from lib.discord_app.runtime import RuntimeServices
from lib.discord_app.security import KeyRing
from lib.discord_app.session_authority import SessionAuthority
from lib.discord_app.storage import ControlStore
from lib.discord_app.supabase_service import ProviderError, SupabaseService

load_dotenv(ROOT / ".env")
load_dotenv(CONFIG_DIR / ".env", override=True)
load_dotenv(CONFIG_DIR / "SUPABASE_PRIVILEGED.env", override=False)

CLOUDINARY_IMPORT_DIR = INSTANCE_DIR / "cloudinary-import"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

keys = KeyRing(INSTANCE_DIR)
store = ControlStore(INSTANCE_DIR / "control.sqlite3", keys)
bootstrapped_settings = migrate_bootstrap_env(ROOT, store)
provider = SupabaseService(store, ROOT)
captcha = HCaptchaService(store)
gmail = GmailConfigService(store)
cloudinary = CloudinaryService(store)
session_authority = SessionAuthority(store, provider, lease_seconds=0.75)
runtime = RuntimeServices(
    store=store, provider=provider, captcha=captcha, gmail=gmail,
    cloudinary=cloudinary, session_authority=session_authority,
)

DATABASE_SCHEMA_VERSION = "9"

def _verify_schema_at_import() -> None:
    if not provider.database_configured:
        return
    try:
        schema_bootstrap = provider.ensure_application_schema()
        store.set_secret("APP_DATABASE_SCHEMA_VERSION", DATABASE_SCHEMA_VERSION, None)
        if schema_bootstrap.get("repaired") or bootstrapped_settings:
            store.add_audit(
                "system", "bootstrap", "database.migration", "success",
                target="current-schema-v9",
                details={"mode": "schema-repair" if schema_bootstrap.get("repaired") else "schema-verified"},
            )
    except ProviderError as exc:
        store.add_audit(
            "system", "bootstrap", "database.migration", "denied",
            target="current-schema-v9", details={"provider_code": exc.code, "mode": "schema-health"},
        )
    except Exception as exc:
        store.add_audit(
            "system", "bootstrap", "database.migration", "failure",
            target="current-schema-v9", details={"error_type": exc.__class__.__name__, "mode": "schema-health"},
        )

_verify_schema_at_import()

COOKIE_SECURE = True
ADMIN_LOCAL_ONLY = os.getenv("ADMIN_LOCAL_ONLY", "1").strip() != "0"
APP_HOSTNAME = os.getenv("APP_HOSTNAME", "discord").strip().lower().rstrip(".") or "discord"
ALLOWED_HOSTS = frozenset({APP_HOSTNAME})

def _voice_ice_servers() -> list[dict[str, Any]]:
    raw = os.getenv("VOICE_ICE_SERVERS_JSON", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                cleaned: list[dict[str, Any]] = []
                for item in parsed[:8]:
                    if not isinstance(item, dict):
                        continue
                    urls = item.get("urls")
                    valid_urls = isinstance(urls, str) or (isinstance(urls, list) and all(isinstance(value, str) for value in urls))
                    if not valid_urls:
                        continue
                    entry: dict[str, Any] = {"urls": urls}
                    if isinstance(item.get("username"), str):
                        entry["username"] = item["username"]
                    if isinstance(item.get("credential"), str):
                        entry["credential"] = item["credential"]
                    cleaned.append(entry)
                if cleaned:
                    return cleaned
        except (TypeError, ValueError):
            pass
    return [
        {"urls": "stun:stun.l.google.com:19302"},
        {"urls": "stun:stun1.l.google.com:19302"},
    ]

VOICE_ICE_SERVERS = _voice_ice_servers()
APP_COOKIE = "app_sid"
APP_PRESENCE_COOKIE = "app_presence"
ADMIN_COOKIE = "admin_sid"

PUBLIC_ROOT_FILES = {
    "discord.css": "text/css",
    "ui.js": "application/javascript",
    "auth-provider.js": "application/javascript",
    "captcha.css": "text/css",
    "channels.css": "text/css",
    "guild.css": "text/css",
}
IMAGE_ASSET_ALIASES = {
    "0085-og_img_discord_home.png": "0084-og_img_discord_home.png",
}
UI_MODULE_FILES = frozenset({
    "bootstrap.js", "captcha.js", "channels.js", "account-verification.js",
    "friends.js", "friend-pending.js", "guild-navigation.js", "date-menu.js",
    "dom.js", "direct-messages.js", "session-watchdog.js", "server-entry.js",
    "voice.js", "voice-capture.js", "voice-sounds.js", "login.js",
    "menu-catalog.js", "overlay-manager.js", "register-form.js",
    "register-validation.js", "runtime.js", "sliding-highlight.js", "state.js",
})
AUTH_SURFACE_PATHS = frozenset({"/", "/login", "/login.html", "/register.html"})
SENSITIVE_AUTH_QUERY_KEYS = frozenset({
    "email", "password", "identifier", "username", "global_name", "phone",
    "token", "access_token", "refresh_token", "hcaptchatoken", "h-captcha-response",
})
PROJECT_REF_RE = re.compile(r"^[a-z0-9]{8,40}$")
GOOGLE_CREDENTIALS_URL = "https://console.cloud.google.com/apis/credentials"
GOOGLE_GMAIL_API_URL = "https://console.cloud.google.com/apis/library/gmail.googleapis.com"
