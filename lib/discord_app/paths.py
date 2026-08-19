from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundled_root() -> Path:
    """Return the immutable application root for source and packaged modes."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.resolve()


PROJECT_ROOT = _bundled_root()
CONFIG_DIR = PROJECT_ROOT / "config"
ASSETS_DIR = PROJECT_ROOT / "assets"
ASSET_CSS_DIR = ASSETS_DIR / "css"
ASSET_JS_DIR = ASSETS_DIR / "js"
UI_JS_DIR = ASSET_JS_DIR / "ui"
PRIV_DIR = PROJECT_ROOT / "priv"
STATIC_DIR = PRIV_DIR / "static"
STATIC_PAGES_DIR = STATIC_DIR / "pages"
STATIC_FONTS_DIR = STATIC_DIR / "fonts"
STATIC_ASSETS_DIR = STATIC_DIR / "assets"
STATIC_IMAGES_DIR = STATIC_DIR / "images"
ARCHITECTURE_DIR = PRIV_DIR / "architecture"
SUPABASE_DIR = PRIV_DIR / "supabase"
SUPABASE_MIGRATIONS_DIR = SUPABASE_DIR / "migrations"
SCRIPTS_DIR = PRIV_DIR / "scripts"

# Desktop installers are immutable and replaced during updates. Runtime state and
# secrets therefore live outside the installation directory when these explicit
# environment paths are supplied by Electron. Source/dev mode retains the legacy
# project-local defaults byte-for-byte.
INSTANCE_DIR = _env_path("DISCORD_INSTANCE_DIR", PROJECT_ROOT / "instance")
RUNTIME_DIR = _env_path("DISCORD_RUNTIME_DIR", PROJECT_ROOT / ".runtime")
PRIVATE_CONFIG_DIR = _env_path("DISCORD_PRIVATE_CONFIG_DIR", CONFIG_DIR)
PRIVATE_ENV_FILE = _env_path(
    "DISCORD_PRIVATE_ENV_FILE",
    PRIVATE_CONFIG_DIR / "SUPABASE_PRIVILEGED.env",
)
