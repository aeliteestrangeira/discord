import re
from flask import abort, render_template, request
from lib.discord_app.security import masked
from lib.discord_app_web.registration import validate_supabase_endpoint_config
from lib.discord_app_web.runtime import (
    APP_HOSTNAME, GMAIL_SEND_SCOPE, GOOGLE_CREDENTIALS_URL, GOOGLE_GMAIL_API_URL,
    captcha, cloudinary, gmail, provider, store,
)
from lib.discord_app_web.security import admin_csrf_token, admin_identity, admin_required, audit, require_admin_csrf

def admin_config():
    admin_id, username = admin_identity()
    message = None
    error = None
    if request.method == "POST":
        require_admin_csrf()
        action = request.form.get("action", "")
        try:
            if action == "save":
                changed: list[str] = []
                replacement_url = (request.form.get("supabase_url") or "").strip()
                replacement_publishable = (request.form.get("publishable_key") or "").strip()
                replacement_ref = (request.form.get("project_ref") or "").strip()
                replacement_db_host = (request.form.get("db_host") or "").strip()
                secret_key = (request.form.get("secret_key") or "").strip()
                service_role_key = (request.form.get("service_role_key") or "").strip()
                legacy_anon_key = (request.form.get("legacy_anon_key") or "").strip()
                legacy_jwt_secret = (request.form.get("legacy_jwt_secret") or "").strip()
                jwks_url = (request.form.get("jwks_url") or "").strip()
                jwks_kid = (request.form.get("jwks_kid") or "").strip()
                db_password = request.form.get("db_password") or ""
                hcaptcha_sitekey = (request.form.get("hcaptcha_sitekey") or "").strip()
                hcaptcha_secret = (request.form.get("hcaptcha_secret") or "").strip()
                gmail_sender = (request.form.get("gmail_sender") or "").strip()
                gmail_client_id = (request.form.get("gmail_client_id") or "").strip()
                gmail_client_secret = (request.form.get("gmail_client_secret") or "").strip()
                gmail_refresh_token = (request.form.get("gmail_refresh_token") or "").strip()

                endpoint_values = [replacement_url, replacement_ref, replacement_db_host]
                if any(endpoint_values):
                    if not all(endpoint_values):
                        raise ValueError("URL, project ref e host PostgreSQL devem ser informados juntos.")
                    url, project_ref, db_host = validate_supabase_endpoint_config(
                        replacement_url, replacement_ref, replacement_db_host
                    )
                    for name, value in (
                        ("SUPABASE_URL", url),
                        ("SUPABASE_PROJECT_REF", project_ref),
                        ("SUPABASE_DB_HOST", db_host),
                    ):
                        store.set_secret(name, value, admin_id)
                        changed.append(name)
                if replacement_publishable:
                    if len(replacement_publishable) > 4096 or not replacement_publishable.startswith("sb_publishable_"):
                        raise ValueError("Chave publicável inválida.")
                    store.set_secret("SUPABASE_PUBLISHABLE_KEY", replacement_publishable, admin_id)
                    changed.append("SUPABASE_PUBLISHABLE_KEY")
                if secret_key:
                    if len(secret_key) > 4096 or not secret_key.startswith("sb_secret_"):
                        raise ValueError("Chave secreta moderna inválida.")
                    store.set_secret("SUPABASE_SECRET_KEY", secret_key, admin_id)
                    changed.append("SUPABASE_SECRET_KEY")
                if service_role_key:
                    if len(service_role_key) > 4096 or service_role_key.count(".") != 2:
                        raise ValueError("Chave service_role legada inválida.")
                    store.set_secret("SUPABASE_SERVICE_ROLE_KEY", service_role_key, admin_id)
                    changed.append("SUPABASE_SERVICE_ROLE_KEY")
                if legacy_anon_key:
                    if len(legacy_anon_key) > 4096 or legacy_anon_key.count(".") != 2:
                        raise ValueError("Chave anon legada inválida.")
                    store.set_secret("SUPABASE_LEGACY_ANON_KEY", legacy_anon_key, admin_id)
                    changed.append("SUPABASE_LEGACY_ANON_KEY")
                if legacy_jwt_secret:
                    if len(legacy_jwt_secret) > 4096:
                        raise ValueError("Legacy JWT secret inválido.")
                    store.set_secret("SUPABASE_JWT_LEGACY_SECRET", legacy_jwt_secret, admin_id)
                    changed.append("SUPABASE_JWT_LEGACY_SECRET")
                if jwks_url:
                    if len(jwks_url) > 2048 or not jwks_url.startswith(provider.url + "/auth/v1/"):
                        raise ValueError("JWKS discovery URL inválida para este projeto.")
                    store.set_secret("SUPABASE_JWKS_URL", jwks_url, admin_id)
                    changed.append("SUPABASE_JWKS_URL")
                if jwks_kid:
                    if not re.fullmatch(r"[A-Za-z0-9._-]{8,128}", jwks_kid):
                        raise ValueError("JWKS KID inválido.")
                    store.set_secret("SUPABASE_JWKS_KID", jwks_kid, admin_id)
                    changed.append("SUPABASE_JWKS_KID")
                if db_password:
                    if len(db_password) > 4096:
                        raise ValueError("Senha do banco inválida.")
                    store.set_secret("SUPABASE_DB_PASSWORD", db_password, admin_id)
                    changed.append("SUPABASE_DB_PASSWORD")
                if hcaptcha_sitekey:
                    store.set_secret("HCAPTCHA_SITE_KEY", captcha.validate_sitekey(hcaptcha_sitekey), admin_id)
                    changed.append("HCAPTCHA_SITE_KEY")
                if hcaptcha_secret:
                    store.set_secret("HCAPTCHA_SECRET", captcha.validate_secret(hcaptcha_secret), admin_id)
                    changed.append("HCAPTCHA_SECRET")
                changed.extend(gmail.save_partial(
                    admin_id=admin_id,
                    sender_email=gmail_sender,
                    client_id=gmail_client_id,
                    client_secret=gmail_client_secret,
                    refresh_token=gmail_refresh_token,
                ))
                audit("admin", username, "config.update", "success", target="security-providers", details={"changed": changed})
                message = "Configuração atualizada." if changed else "Nenhum valor foi alterado."
            elif action == "clear-secret":
                store.delete_secret("SUPABASE_SECRET_KEY")
                audit("admin", username, "config.clear", "success", target="SUPABASE_SECRET_KEY")
                message = "Chave secreta removida."
            elif action == "clear-db":
                store.delete_secret("SUPABASE_DB_PASSWORD")
                audit("admin", username, "config.clear", "success", target="SUPABASE_DB_PASSWORD")
                message = "Senha do banco removida."
            elif action == "test-public":
                ok, detail = provider.test_public_connection()
                audit("admin", username, "supabase.connection_test", "success" if ok else "failure", target="public", details={"detail": detail})
                message = f"Conexão pública: {'OK' if ok else 'FALHA'} ({detail})."
            elif action == "test-admin":
                ok, detail = provider.test_admin_connection()
                audit("admin", username, "supabase.admin_test", "success" if ok else "failure", target=provider.admin_key_kind, details={"detail": detail})
                message = f"Auth Admin: {'OK' if ok else 'FALHA'} ({detail})."
            elif action == "test-jwks":
                ok, detail = provider.test_jwks()
                audit("admin", username, "supabase.jwks_test", "success" if ok else "failure", target=provider.jwks_kid or "jwks", details={"detail": detail})
                message = f"JWKS: {'OK' if ok else 'FALHA'} ({detail})."
            elif action == "test-legacy":
                ok, detail = provider.verify_legacy_api_keys()
                audit("admin", username, "supabase.legacy_key_test", "success" if ok else "failure", target="legacy-api-keys", details={"detail": detail})
                message = f"Conjunto legado: {'OK' if ok else 'FALHA'} ({detail})."
            elif action == "test-db":
                detail = provider.database_health()
                audit("admin", username, "database.connection_test", "success", target=detail.get("database"), details={"user": detail.get("user"), "version": detail.get("version")})
                message = f"PostgreSQL: OK ({detail.get('database')} / {detail.get('user')} / {detail.get('version')})."
            elif action == "clear-service-role":
                store.delete_secret("SUPABASE_SERVICE_ROLE_KEY")
                audit("admin", username, "config.clear", "success", target="SUPABASE_SERVICE_ROLE_KEY")
                message = "Chave service_role removida."
            elif action == "clear-legacy-jwt":
                store.delete_secret("SUPABASE_JWT_LEGACY_SECRET")
                audit("admin", username, "config.clear", "success", target="SUPABASE_JWT_LEGACY_SECRET")
                message = "Legacy JWT secret removido."
            elif action == "clear-gmail":
                gmail.clear()
                audit("admin", username, "config.clear", "success", target="google-gmail-oauth")
                message = "Credenciais futuras do Gmail removidas."
            else:
                abort(400)
        except Exception as exc:
            audit("admin", username, "config.update", "failure", target="supabase", details={"error_type": exc.__class__.__name__})
            error = "A operação não foi concluída. Consulte a auditoria."

    return render_template(
        "admin/config.html",
        username=username,
        csrf=admin_csrf_token(),
        message=message,
        error=error,
        supabase_url=provider.url,
        project_ref=provider.project_ref,
        publishable_masked=masked(provider.publishable_key),
        secret_masked=masked(provider.secret_key),
        service_role_masked=masked(provider.service_role_key),
        legacy_anon_masked=masked(provider.legacy_anon_key),
        legacy_jwt_masked=masked(provider.legacy_jwt_secret),
        jwks_url=provider.jwks_url,
        jwks_kid=provider.jwks_kid,
        admin_key_kind=provider.admin_key_kind,
        secret_configured=provider.admin_configured,
        db_configured=provider.database_configured,
        db_host=provider.db_host,
        db_password_masked=masked(provider.db_password),
        hcaptcha_sitekey=captcha.sitekey,
        hcaptcha_secret_masked=masked(captcha.secret),
        hcaptcha_configured=captcha.configured,
        app_hostname=APP_HOSTNAME,
        gmail_active_provider=gmail.active_provider,
        gmail_configured=gmail.configured,
        gmail_sender=gmail.sender_email,
        gmail_client_id_masked=masked(gmail.client_id),
        gmail_client_secret_masked=masked(gmail.client_secret),
        gmail_refresh_token_masked=masked(gmail.refresh_token),
        gmail_send_scope=GMAIL_SEND_SCOPE,
        google_credentials_url=GOOGLE_CREDENTIALS_URL,
        google_gmail_api_url=GOOGLE_GMAIL_API_URL,
        cloudinary_configured=cloudinary.configured,
        cloudinary_cloud_name=cloudinary.cloud_name,
        cloudinary_api_key_masked=masked(cloudinary.api_key),
        cloudinary_api_secret_masked=masked(cloudinary.api_secret),
        cloudinary_folder=cloudinary.folder,
    )


def register_routes(app) -> None:
    app.add_url_rule("/admin/config", view_func=admin_required(admin_config), methods=["GET", "POST"])
