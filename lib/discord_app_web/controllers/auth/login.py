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

def api_login():
    raw, _ = require_browser_csrf()
    payload = request.get_json(silent=True) or {}
    try:
        identifier, password = validate_login(payload.get("identifier"), payload.get("password"))
    except ValidationError as exc:
        audit("anonymous", None, "auth.login", "rejected", details={"reason": "validation"})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "validation", "message": str(exc)}}), 400

    identifier_digest = sha256_text(identifier.lower())
    rate_bucket = f"login:{request.remote_addr or 'unknown'}:{identifier_digest}"
    if not store.allow_rate(rate_bucket, limit=10, window_seconds=300):
        audit("anonymous", identifier_digest, "auth.login", "rate_limited")
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas. Aguarde antes de tentar novamente."}}), 429

    # Human verification is mandatory before either the local administrator or
    # the remote identity provider is consulted. The secret remains server-side
    # and hCaptcha tokens are not logged or persisted.
    captcha_token = str(payload.get("hcaptchaToken") or "").strip()
    if not captcha.configured:
        audit("anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha", details={"reason": "not_configured"})
        return jsonify({"configured": False, "ok": False, "error": {"code": "captcha_not_configured", "message": "Verificação humana não configurada."}}), 503
    if not captcha_token:
        audit("anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha", details={"reason": "missing_token"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_required", "message": "Confirme que você é humano."}}), 403
    try:
        captcha_result = captcha.verify(captcha_token, request.remote_addr)
    except HCaptchaError as exc:
        audit("anonymous", identifier_digest, "captcha.verify", "failure", target="hcaptcha", details={"provider_code": exc.code})
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_unavailable", "message": exc.public_message}}), 503
    if not captcha_result.success:
        audit(
            "anonymous", identifier_digest, "captcha.verify", "denied", target="hcaptcha",
            details={"error_codes": list(captcha_result.error_codes), "hostname": captcha_result.hostname},
        )
        return jsonify({"configured": True, "ok": False, "error": {"code": "captcha_denied", "message": "A confirmação humana não foi aceita."}}), 403
    audit("anonymous", identifier_digest, "captcha.verify", "success", target="hcaptcha", details={"hostname": captcha_result.hostname})

    # One login surface, two server-side identity authorities. Local administrator
    # authentication is accepted only from loopback when ADMIN_LOCAL_ONLY is on.
    # Remote callers never receive a distinct response revealing that a local
    # administrator identifier exists.
    admin_ok, admin_row, admin_reason = store.authenticate_admin(identifier, password)
    if admin_row is not None and ADMIN_LOCAL_ONLY and not is_loopback(request.remote_addr):
        admin_row = None
        admin_ok = False
        admin_reason = "local_only"
    if admin_row is not None:
        username = str(admin_row["username"])
        if not admin_ok:
            audit("admin", username, "auth.login", "denied", target="local-admin", details={"reason": admin_reason})
            return jsonify({"configured": True, "ok": False, "error": {"code": "auth_denied", "message": "Não foi possível autenticar com as credenciais informadas."}}), 401

        admin_id = int(admin_row["id"])
        new_raw = store.authenticate_browser_session(
            old_raw=raw,
            user_id=f"local-admin:{admin_id}",
            email="",
            access_token=None,
            refresh_token=None,
            expires_at_epoch=None,
            role="admin",
        )
        admin_raw = store.create_admin_session(admin_id)
        audit("admin", username, "auth.login", "success", target="local-admin")
        response = jsonify({
            "configured": True,
            "ok": True,
            "status": "authenticated",
            "role": "admin",
            "redirect": "/admin",
            "csrfToken": keys.csrf_for_session(new_raw),
            "user": {"id": f"local-admin:{admin_id}", "username": username, "email": ""},
        })
        set_app_cookie(response, new_raw)
        set_admin_cookie(response, admin_raw)
        return response

    # Do not pre-query auth.users for account existence. Unknown accounts and
    # wrong passwords follow the same public authentication path and response.
    # The provider remains the identity authority, removing a direct account-
    # account-enumeration side channel and an unnecessary privileged database lookup.

    pending_provider_proof = False
    try:
        result = provider.sign_in(identifier, password)
    except ProviderError as exc:
        # Hosted Supabase normally blocks password sign-in for an unconfirmed
        # email.  Importantly, Auth returns ``email_not_confirmed`` only after it
        # has already validated the password and rejected banned users.  Treat
        # that exact provider result as proof of credentials, then resolve only
        # the identity server-side and create a restricted local ``pending``
        # session.  No Supabase access/refresh token is minted or exposed.
        if exc.code == "email_not_confirmed" and "@" in identifier:
            try:
                result = provider.pending_email_identity(identifier)
                # Confirmation can race with the provider error (for example an
                # administrator confirms the account in another tab).  If that
                # happened, retry the normal provider login so a confirmed user
                # receives a real Supabase session instead of a local pending one.
                if bool(result.get("email_confirmed")):
                    result = provider.sign_in(identifier, password)
                else:
                    pending_provider_proof = True
            except ProviderError as pending_exc:
                audit(
                    "anonymous", identifier_digest, "auth.login", "denied", target="supabase-auth",
                    details={"provider_code": pending_exc.code, "initial_provider_code": exc.code},
                )
                status = 503 if pending_exc.code in {"not_configured", "db_password_missing", "dependency_missing", "pending_identity_lookup_failed"} else 401
                return jsonify({
                    "configured": provider.public_configured,
                    "ok": False,
                    "error": {"code": "auth_denied", "message": "Não foi possível autenticar com as credenciais informadas."},
                }), status
        else:
            audit("anonymous", identifier_digest, "auth.login", "denied", target="supabase-auth", details={"provider_code": exc.code})
            status = 503 if exc.code == "not_configured" else 401
            return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "auth_denied", "message": "Não foi possível autenticar com as credenciais informadas."}}), status

    user_id = result.get("user_id") or ""
    email = result.get("email") or ""
    email_confirmed = bool(result.get("email_confirmed", False))
    role = "user" if email_confirmed else "pending"
    if not user_id:
        audit("anonymous", identifier_digest, "auth.login", "failure", target="supabase-auth", details={"reason": "missing_user_id"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "auth_denied", "message": "Não foi possível concluir a autenticação."}}), 502
    if role == "user" and not result.get("has_session"):
        audit("anonymous", identifier_digest, "auth.login", "failure", target="supabase-auth", details={"reason": "confirmed_session_missing"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "auth_denied", "message": "Não foi possível concluir a autenticação."}}), 502

    new_raw = store.authenticate_browser_session(
        old_raw=raw,
        user_id=user_id,
        email=email,
        access_token=result.get("access_token"),
        refresh_token=result.get("refresh_token"),
        expires_at_epoch=result.get("expires_at"),
        role=role,
        username=result.get("username") or "",
        global_name=result.get("global_name") or "",
        email_confirmed=email_confirmed,
        verification_kind=str(result.get("verification_kind") or "signup"),
    )
    existing_admin_raw = request.cookies.get(ADMIN_COOKIE, "")
    if existing_admin_raw:
        store.delete_admin_session(existing_admin_raw)
    audit(
        "user", user_id, "auth.login", "success",
        target="local-pending-session" if role == "pending" else "supabase-auth",
        details={
            "role": role,
            "confirmation_pending": role == "pending",
            "credential_proof": "supabase-email-not-confirmed" if pending_provider_proof else "supabase-session",
        },
    )
    response = jsonify({
        "configured": True,
        "ok": True,
        "status": "confirmation-pending" if role == "pending" else "authenticated",
        "role": role,
        "redirect": "/channels/@me",
        "csrfToken": keys.csrf_for_session(new_raw),
        "user": {
            "id": user_id,
            "email": email,
            "phone": result.get("phone") or "",
            "username": result.get("username") or "",
            "globalName": result.get("global_name") or "",
            "emailConfirmed": email_confirmed,
        },
    })
    set_app_cookie(response, new_raw)
    if existing_admin_raw:
        clear_admin_cookie(response)
    return response

def api_login_link():
    require_browser_csrf()
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier") or "").strip()
    if not identifier or len(identifier) > 999:
        audit("anonymous", None, "auth.login_link", "rejected", details={"reason": "validation"})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "validation", "message": "Identificador obrigatório."}}), 400

    identifier_digest = sha256_text(identifier.lower())
    # Treat only phone-shaped values as phone numbers. Arbitrary text such as
    # "ee" remains on the email recovery path, matching the captured UI
    # behavior for a non-existent email/identifier.
    phone_candidate = "".join(ch for ch in identifier if ch.isdigit())
    phone_shaped = identifier.startswith("+") or (phone_candidate == identifier and len(phone_candidate) >= 6)
    channel = "phone" if phone_shaped else "email"
    rate_bucket = f"login-link:{request.remote_addr or 'unknown'}:{identifier_digest}"
    if not store.allow_rate(rate_bucket, limit=5, window_seconds=900):
        audit("anonymous", identifier_digest, "auth.login_link", "rate_limited", target="supabase-auth", details={"channel": channel})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "rate_limited", "message": "Muitas solicitações. Aguarde antes de tentar novamente."}}), 429

    if not provider.public_configured:
        audit("anonymous", identifier_digest, "auth.login_link", "denied", target="supabase-auth", details={"reason": "not_configured", "channel": channel})
        return jsonify({"configured": False, "ok": False, "error": {"code": "not_configured", "message": "Provedor de autenticação não configurado."}}), 503

    # Recovery must not reveal whether an account exists. Submit the request to
    # the provider without a privileged auth.users existence query. The public
    # response remains generic for both existing and non-existing identities.

    try:
        provider_channel = provider.request_login_link(identifier)
        audit("anonymous", identifier_digest, "auth.login_link", "requested", target="supabase-auth", details={"channel": provider_channel})
    except ProviderError as exc:
        audit("anonymous", identifier_digest, "auth.login_link", "provider_rejected", target="supabase-auth", details={"provider_code": exc.code, "channel": channel})
        # Intentional indistinguishable response: recovery is advisory and must
        # not become an account-existence side channel. Operational failures remain in
        # the server-side audit trail for administrators.
        return jsonify({
            "configured": True,
            "ok": True,
            "status": "login-link-requested",
            "channel": channel,
            "message": "Se a conta existir e estiver apta, as instruções serão enviadas.",
        }), 202

    return jsonify({
        "configured": True,
        "ok": True,
        "status": "login-link-requested",
        "channel": channel,
        "message": "Se a conta existir e estiver apta, as instruções serão enviadas.",
    }), 202

def register_routes(app) -> None:
    app.add_url_rule("/api/auth/login", view_func=api_login, methods=["POST"])
    app.add_url_rule("/api/auth/login-link", view_func=api_login_link, methods=["POST"])
