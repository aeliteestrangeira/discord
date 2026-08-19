from __future__ import annotations

import os
from pathlib import Path

from .storage import ControlStore

BOOTSTRAP_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_LEGACY_ANON_KEY",
    "SUPABASE_JWT_LEGACY_SECRET",
    "SUPABASE_JWKS_URL",
    "SUPABASE_JWKS_KID",
    "SUPABASE_JWKS_PREVIOUS_KID",
    "SUPABASE_JWKS_STATIC_JSON",
    "SUPABASE_PROJECT_REF",
    "SUPABASE_DB_HOST",
    "SUPABASE_DB_PASSWORD",
    "HCAPTCHA_SITE_KEY",
    "HCAPTCHA_SECRET",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
    "CLOUDINARY_FOLDER",
)

BOOTSTRAP_FILES = (".env", "config/SUPABASE_PRIVILEGED.env")


def migrate_bootstrap_env(root: Path, store: ControlStore) -> list[str]:
    """Import bootstrap values into encrypted storage without modifying their source files.

    Existing encrypted settings always win. Bootstrap files are treated as
    administrator-owned deployment input and must remain byte-for-byte intact:
    importing configuration must never erase credentials from ``.env`` or
    ``config/SUPABASE_PRIVILEGED.env``. This also prevents a later private deployment
    package from becoming unconfigured merely because the application started
    once before it was archived.
    """
    newly_stored: list[str] = []
    discovered: list[str] = []

    for name in BOOTSTRAP_KEYS:
        value = os.getenv(name, "").strip()
        if not value:
            continue
        discovered.append(name)
        if not store.get_secret(name):
            store.set_secret(name, value, None)
            newly_stored.append(name)

    if discovered:
        store.add_audit(
            "system",
            "bootstrap",
            "config.bootstrap",
            "success",
            target="encrypted-local-store",
            details={"preserved": sorted(discovered), "stored": sorted(newly_stored)},
        )
    return newly_stored
