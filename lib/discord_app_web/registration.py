from __future__ import annotations

import re
from flask import jsonify

from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.runtime import DATABASE_SCHEMA_VERSION, PROJECT_REF_RE, provider, store

SUPABASE_URL_RE = re.compile(r"^https://([a-z0-9]{8,40})\.supabase\.co$")

def registration_schema_ready(*, repair: bool = True) -> bool:
    if not provider.database_configured:
        return False
    try:
        # Registration is admitted only when the complete application schema is
        # healthy. This keeps the private migration ledger and delivery telemetry
        # synchronized with the public profile invariants instead of treating them
        # as an unrelated best-effort database.
        status = provider.application_schema_status()
        migration = provider.migration_status()
        ready = bool(status.get("ready") and migration.get("ready"))
        if not ready and repair:
            status = provider.ensure_application_schema()
            ready = bool(status.get("ready"))
        if ready and store.get_secret("APP_DATABASE_SCHEMA_VERSION") != DATABASE_SCHEMA_VERSION:
            store.set_secret("APP_DATABASE_SCHEMA_VERSION", DATABASE_SCHEMA_VERSION, None)
        return ready
    except ProviderError:
        return False

def registration_readiness_error(schema_message: str):
    """Return a precise configuration/schema failure instead of conflating them."""
    if not provider.public_configured:
        return jsonify({
            "configured": False,
            "ok": False,
            "error": {"code": "not_configured", "message": "Provedor de autenticação não configurado."},
        }), 503
    if not provider.database_configured:
        return jsonify({
            "configured": True,
            "ok": False,
            "error": {"code": "database_not_configured", "message": "Conexão PostgreSQL do projeto não configurada."},
        }), 503
    if not registration_schema_ready():
        return jsonify({
            "configured": True,
            "ok": False,
            "error": {"code": "schema_not_ready", "message": schema_message},
        }), 503
    return None

def validate_supabase_endpoint_config(url: str, project_ref: str, db_host: str) -> tuple[str, str, str]:
    url = url.strip().rstrip("/")
    project_ref = project_ref.strip().lower()
    db_host = db_host.strip().lower()
    match = SUPABASE_URL_RE.fullmatch(url)
    if not match or not PROJECT_REF_RE.fullmatch(project_ref):
        raise ValueError("Configuração do projeto inválida.")
    if match.group(1) != project_ref:
        raise ValueError("URL e project ref não correspondem.")
    expected_db_host = f"db.{project_ref}.supabase.co"
    if db_host != expected_db_host:
        raise ValueError("Host PostgreSQL não corresponde ao project ref.")
    return url, project_ref, db_host
