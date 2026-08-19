from __future__ import annotations

import re
import secrets
import time
import unicodedata

from flask import abort, jsonify, request

from lib.discord_app.access import Actor, Policy
from lib.discord_app.hcaptcha_service import HCaptchaError
from lib.discord_app.security import constant_equal, is_loopback, sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app.validators import ValidationError, validate_login, validate_registration
from lib.discord_app_web.registration import registration_readiness_error
from lib.discord_app_web.runtime import (
    ADMIN_COOKIE, ADMIN_LOCAL_ONLY, APP_COOKIE, APP_HOSTNAME, APP_PRESENCE_COOKIE,
    captcha, keys, provider, store,
)
from lib.discord_app_web.security import (
    BrowserSessionRevoked, audit, clear_admin_cookie, clear_app_cookie,
    current_browser_session, require_browser_csrf, require_live_user_identity,
    set_admin_cookie, set_app_cookie,
)

def _username_candidate_base(display_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    compact = re.sub(r"[^a-z0-9_.]+", "", ascii_text)
    compact = re.sub(r"\.{2,}", ".", compact)
    compact = compact.strip("._")
    return compact or "usuario"

def api_username_check():
    require_browser_csrf()
    readiness_error = registration_readiness_error("Validação de nome de usuário indisponível até a migração do banco ser concluída.")
    if readiness_error:
        return readiness_error
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.]{2,32}", username):
        return jsonify({"ok": False, "error": {"code": "username_invalid", "message": "Nome de usuário inválido."}}), 400
    if ".." in username:
        return jsonify({"ok": False, "error": {"code": "username_repeating_dots", "message": "Nome de usuário não pode conter pontos repetidos."}}), 400

    digest = sha256_text(username.lower())
    bucket = f"username-check:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=60, window_seconds=60):
        audit("anonymous", digest, "auth.username.check", "rate_limited")
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitas verificações. Aguarde um momento."}}), 429
    try:
        exists = provider.username_exists(username)
    except ProviderError as exc:
        audit("anonymous", digest, "auth.username.check", "failure", target="database", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": "lookup_unavailable", "message": "Não foi possível verificar o nome de usuário agora."}}), 503
    return jsonify({"ok": True, "available": not exists})

def api_username_suggest():
    require_browser_csrf()
    readiness_error = registration_readiness_error("Sugestão de nome de usuário indisponível até a migração do banco ser concluída.")
    if readiness_error:
        return readiness_error
    payload = request.get_json(silent=True) or {}
    display_name = str(payload.get("displayName") or "").strip()[:64]
    if not display_name:
        return jsonify({"ok": True, "suggestion": None})

    bucket = f"username-suggest:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=20, window_seconds=60):
        audit("anonymous", None, "auth.username.suggest", "rate_limited")
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitas sugestões. Aguarde um momento."}}), 429

    base = _username_candidate_base(display_name)
    candidates: list[str] = []
    seen: set[str] = set()
    for _ in range(48):
        suffix = f"{secrets.randbelow(100000):05d}"
        candidate = f"{base[:32-len(suffix)]}{suffix}"
        if len(candidate) < 2:
            candidate = f"usuario{suffix}"
        if candidate in seen:
            continue
        seen.add(candidate)
        candidates.append(candidate)
        if len(candidates) >= 24:
            break

    try:
        existing = provider.existing_usernames(candidates)
    except ProviderError as exc:
        audit("anonymous", None, "auth.username.suggest", "failure", target="database", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": "lookup_unavailable", "message": "Não foi possível gerar uma sugestão agora."}}), 503

    for candidate in candidates:
        if candidate not in existing:
            return jsonify({"ok": True, "suggestion": candidate})

    return jsonify({"ok": False, "error": {"code": "suggestion_unavailable", "message": "Não foi possível gerar uma sugestão agora."}}), 503

def api_register():
    raw, _ = require_browser_csrf()
    readiness_error = registration_readiness_error("Cadastro temporariamente indisponível até a migração do banco ser concluída.")
    if readiness_error:
        return readiness_error
    payload = request.get_json(silent=True) or {}
    try:
        email, password, metadata = validate_registration(payload)
    except ValidationError as exc:
        audit("anonymous", None, "auth.register", "rejected", details={"reason": "validation"})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "validation", "message": str(exc)}}), 400

    identifier_digest = sha256_text(email)
    rate_bucket = f"register:{request.remote_addr or 'unknown'}:{identifier_digest}"
    if not store.allow_rate(rate_bucket, limit=5, window_seconds=600):
        audit("anonymous", identifier_digest, "auth.register", "rate_limited")
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas. Aguarde antes de tentar novamente."}}), 429

    # The trusted Auth Admin registration path must never be reachable solely
    # with an anonymous browser session + CSRF token. Require the same human
    # verification gate used by login before any username/database/Auth side
    # effect. hCaptcha secrets remain server-side and tokens are never audited.
    captcha_token = str(payload.get("hcaptchaToken") or "").strip()
    if not captcha.configured:
        audit("anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha", details={"reason": "not_configured", "flow": "register"})
        return jsonify({"configured": False, "ok": False, "error": {"code": "captcha_not_configured", "message": "Verificação humana não configurada."}}), 503
    if not captcha_token:
        audit("anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha", details={"reason": "missing_token", "flow": "register"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_required", "message": "Confirme que você é humano."}}), 403
    try:
        captcha_result = captcha.verify(captcha_token, request.remote_addr)
    except HCaptchaError as exc:
        audit("anonymous", identifier_digest, "captcha.verify", "failure", target="hcaptcha", details={"provider_code": exc.code, "flow": "register"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_unavailable", "message": exc.public_message}}), 503
    if not captcha_result.success:
        audit(
            "anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha",
            details={"error_codes": list(captcha_result.error_codes), "hostname": captcha_result.hostname, "flow": "register"},
        )
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_denied", "message": "A confirmação humana não foi aceita."}}), 403
    audit("anonymous", identifier_digest, "captcha.verify", "success", target="hcaptcha", details={"hostname": captcha_result.hostname, "flow": "register"})

    username = str(metadata.get("username") or "")
    try:
        if provider.username_exists(username):
            audit("anonymous", sha256_text(username.lower()), "auth.register", "rejected", target="username", details={"reason": "unavailable"})
            return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "username_unavailable", "message": "Nome de usuário indisponível."}}), 409
    except ProviderError as exc:
        audit("anonymous", sha256_text(username.lower()), "auth.register", "failure", target="username", details={"provider_code": exc.code})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "username_lookup_unavailable", "message": "Não foi possível verificar o nome de usuário agora."}}), 503

    # Registration is owned by this trusted backend.  When an Auth Admin key is
    # configured (the same authority already used by the local administrator),
    # create the unconfirmed user directly through Auth Admin after all local
    # validation/uniqueness/schema gates have passed.  This avoids coupling
    # application registration to the project's public /signup policy while
    # keeping the privileged key entirely server-side.  A public sign-up remains
    # a compatibility fallback only for deployments without Auth Admin authority.
    try:
        if provider.admin_configured:
            result = provider.create_registration_user(email, password, metadata)
        else:
            result = provider.sign_up(email, password, metadata)
    except ProviderError as exc:
        audit(
            "anonymous", identifier_digest, "auth.register", "denied",
            target=f"supabase-auth:{exc.code[:64]}",
            details={"provider_code": exc.code, "registration_authority": "server-admin" if provider.admin_configured else "public-signup"},
        )
        if exc.code == "username_unavailable":
            return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "username_unavailable", "message": "Nome de usuário indisponível."}}), 409
        if exc.code == "email_exists":
            return jsonify({
                "configured": provider.public_configured,
                "ok": False,
                "error": {"code": "registration_denied", "message": "Não foi possível concluir o cadastro com os dados informados."},
            }), 400
        status = 503 if exc.code in {"not_configured", "admin_key_missing", "db_password_missing", "schema_not_ready"} else 400
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "registration_denied", "message": exc.public_message}}), status

    user_id = result.get("user_id") or ""
    if not user_id:
        audit("anonymous", identifier_digest, "auth.register", "failure", target="supabase-auth", details={"reason": "missing_user_id"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "registration_incomplete", "message": "O provedor criou uma resposta de cadastro inválida."}}), 502

    confirmation_email_sent = bool(result.get("confirmation_email_sent"))
    if not bool(result.get("email_confirmed")):
        creation_mode = str(result.get("creation_mode") or "")
        if creation_mode == "server-admin-create":
            provider.record_email_delivery_event(
                user_id=user_id, email=result.get("email") or email, purpose="email_verification", provider="supabase",
                outcome="requested" if confirmation_email_sent else "failed", provider_code=str(result.get("confirmation_email_code") or ""),
            )
        elif creation_mode in {"public-signup", "server-invite"}:
            provider.record_email_delivery_event(
                user_id=user_id, email=result.get("email") or email, purpose="email_verification", provider="supabase", outcome="requested",
            )

    has_provider_session = bool(result.get("has_session"))
    email_confirmed = bool(result.get("email_confirmed")) or has_provider_session
    role = "user" if email_confirmed else "pending"
    new_raw = store.authenticate_browser_session(
        old_raw=raw,
        user_id=user_id,
        email=result.get("email") or email,
        access_token=result.get("access_token") if has_provider_session else None,
        refresh_token=result.get("refresh_token") if has_provider_session else None,
        expires_at_epoch=result.get("expires_at") if has_provider_session else None,
        role=role,
        username=str(metadata.get("username") or ""),
        global_name=str(metadata.get("global_name") or ""),
        email_confirmed=email_confirmed,
        verification_kind=str(result.get("verification_kind") or "signup"),
    )
    response_payload = {
        "configured": True,
        "ok": True,
        "status": "authenticated" if role == "user" else "confirmation-pending",
        "confirmationPending": role == "pending",
        "role": role,
        "redirect": "/channels/@me",
        "csrfToken": keys.csrf_for_session(new_raw),
        "user": {
            "id": user_id,
            "email": result.get("email") or email,
            "username": str(metadata.get("username") or ""),
            "globalName": str(metadata.get("global_name") or ""),
            "emailConfirmed": email_confirmed,
        },
    }
    response = jsonify(response_payload)
    set_app_cookie(response, new_raw)
    existing_admin_raw = request.cookies.get(ADMIN_COOKIE, "")
    if existing_admin_raw:
        store.delete_admin_session(existing_admin_raw)
        clear_admin_cookie(response)
    audit(
        "user" if user_id else "anonymous",
        user_id or identifier_digest,
        "auth.register",
        "success",
        target="supabase-auth",
        details={
            "confirmation_pending": role == "pending",
            "creation_mode": str(result.get("creation_mode") or "public-signup"),
            "verification_kind": str(result.get("verification_kind") or "signup"),
            "confirmation_email_sent": result.get("confirmation_email_sent") if "confirmation_email_sent" in result else None,
        },
    )
    if role == "pending" and result.get("creation_mode") == "server-admin-create" and result.get("confirmation_email_sent") is False:
        audit(
            "user", user_id, "auth.register.confirmation-email", "failure", target="supabase-auth",
            details={"provider_code": str(result.get("confirmation_email_code") or "email_delivery_failed")},
        )
    return response

def register_routes(app) -> None:
    app.add_url_rule("/api/auth/username/check", view_func=api_username_check, methods=["POST"])
    app.add_url_rule("/api/auth/username/suggest", view_func=api_username_suggest, methods=["POST"])
    app.add_url_rule("/api/auth/register", view_func=api_register, methods=["POST"])
