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

def api_session():
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "session.read"):
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "role": actor.role,
        "user": {
            "id": actor.id,
            "email": row["email"] or "",
            "username": row["username"] or "",
            "globalName": row["global_name"] or "",
            "emailConfirmed": bool(row["email_confirmed"]),
        },
    })

def api_session_validate():
    started = time.perf_counter()
    # Read-only liveness endpoint: no CSRF token is needed. Keeping this path
    # independent from the CSRF bootstrap removes a network dependency from the
    # session watchdog and makes cookie removal observable on the very next GET.
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    actor = Actor.from_browser_session(row)
    if actor.role not in {"user", "pending"} or not Policy.allowed(actor, "session.read"):
        raise BrowserSessionRevoked()
    # Liveness endpoint returns only what the watchdog consumes. Identity, role
    # and verification state are already bootstrapped server-side and must not
    # be retransmitted on every liveness check.
    response = jsonify({"ok": True, "authenticated": True})
    response.headers["Server-Timing"] = f"session;dur={(time.perf_counter() - started) * 1000.0:.2f}"
    return response

def api_verification_status():
    raw, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "email.verify.refresh"):
        return jsonify({"ok": False, "error": {"code": "not_pending", "message": "A conta não está aguardando verificação."}}), 403
    try:
        status = provider.auth_user_status(actor.id)
    except ProviderError as exc:
        audit("user", actor.id, "auth.email.status", "failure", target="supabase-auth", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": "status_unavailable", "message": "Não foi possível atualizar o estado da verificação agora."}}), 503

    confirmed = bool(status.get("email_confirmed"))
    updated = store.update_browser_session_identity(
        raw,
        role="user" if confirmed else "pending",
        email=status.get("email") or row["email"] or "",
        username=status.get("username") or row["username"] or "",
        global_name=status.get("global_name") or row["global_name"] or "",
        email_confirmed=confirmed,
    )
    audit("user", actor.id, "auth.email.status", "confirmed" if confirmed else "pending", target="supabase-auth")
    return jsonify({
        "ok": True,
        "authenticated": True,
        "role": "user" if confirmed else "pending",
        "user": {
            "id": actor.id,
            "email": (updated["email"] if updated else status.get("email")) or "",
            "username": (updated["username"] if updated else status.get("username")) or "",
            "globalName": (updated["global_name"] if updated else status.get("global_name")) or "",
            "emailConfirmed": confirmed,
        },
    })

def api_resend_confirmation():
    _, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "email.resend"):
        return jsonify({"ok": False, "error": {"code": "not_pending", "message": "A conta não está aguardando verificação."}}), 403
    email = str(row["email"] or "").strip().lower()
    bucket = f"resend-confirmation:{request.remote_addr or 'unknown'}:{sha256_text(actor.id)}"
    if not store.allow_rate(bucket, limit=3, window_seconds=600):
        audit("user", actor.id, "auth.email.resend", "rate_limited", target="supabase-auth")
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Aguarde antes de reenviar outro e-mail."}}), 429
    verification_kind = str(row["verification_kind"] or "signup") if "verification_kind" in row.keys() else "signup"
    try:
        if verification_kind == "invite":
            provider.invite_user(email)
        else:
            provider.resend_signup_confirmation(email)
    except ProviderError as exc:
        provider.record_email_delivery_event(
            user_id=actor.id, email=email, purpose="email_verification", provider="supabase", outcome="failed", provider_code=exc.code,
        )
        audit(
            "user", actor.id, "auth.email.resend", "failure", target="supabase-auth",
            details={"provider_code": exc.code, "verification_kind": verification_kind},
        )
        return jsonify({"ok": False, "error": {"code": "resend_failed", "message": exc.public_message}}), 503
    provider.record_email_delivery_event(
        user_id=actor.id, email=email, purpose="email_verification", provider="supabase", outcome="requested",
    )
    audit("user", actor.id, "auth.email.resend", "success", target="supabase-auth", details={"verification_kind": verification_kind})
    return jsonify({"ok": True, "message": "E-mail de verificação reenviado."})

def api_change_email():
    raw, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "email.change"):
        abort(403)
    payload = request.get_json(silent=True) or {}
    new_email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")
    if not new_email or not password:
        return jsonify({"ok": False, "error": {"code": "validation", "message": "Preencha o e-mail e a senha."}}), 400
    if len(new_email) > 320 or len(password) > 4096:
        return jsonify({"ok": False, "error": {"code": "validation", "message": "Dados inválidos."}}), 400

    bucket = f"change-email:{sha256_text(actor.id)}:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=6, window_seconds=900):
        audit("user", actor.id, "auth.email.change", "rate_limited", target="supabase-auth")
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas. Aguarde antes de tentar novamente."}}), 429

    current_email = str(row["email"] or "").strip().lower()
    try:
        result = provider.change_account_email(actor.id, current_email, new_email, password)
    except ProviderError as exc:
        audit("user", actor.id, "auth.email.change", "denied", target="supabase-auth", details={"provider_code": exc.code})
        status = 401 if exc.code == "password_mismatch" else 409 if exc.code == "email_exists" else 400 if exc.code in {"email_invalid", "validation"} else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status

    # Email change invalidates the privilege assumptions of the previous provider
    # session. Keep the browser authenticated only as a restricted local pending
    # actor and discard any old Supabase access/refresh tokens.
    store.update_browser_session_identity(
        raw,
        role="pending",
        email=new_email,
        email_confirmed=False,
        verification_kind="signup",
        clear_provider_tokens=True,
    )
    provider.record_email_delivery_event(
        user_id=actor.id,
        email=new_email,
        purpose="email_verification",
        provider="supabase",
        outcome="requested" if result.get("confirmation_email_sent") else "failed",
        provider_code=str(result.get("confirmation_email_code") or ""),
    )
    audit(
        "user", actor.id, "auth.email.change", "success", target="supabase-auth",
        details={"confirmation_pending": True, "confirmation_email_sent": bool(result.get("confirmation_email_sent"))},
    )
    return jsonify({
        "ok": True,
        "email": new_email,
        "emailConfirmed": False,
        "confirmationEmailSent": bool(result.get("confirmation_email_sent")),
        "message": "E-mail alterado. Verifique o novo endereço para confirmar sua conta.",
    })

def api_logout():
    raw, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    store.delete_browser_session(raw)
    if actor.role == "admin" and Policy.allowed(actor, "session.logout"):
        store.delete_admin_session(request.cookies.get(ADMIN_COOKIE, ""))
        audit("admin", actor.id, "auth.logout", "success")
    else:
        audit("user", actor.id if actor.authenticated else None, "auth.logout", "success")
    response = jsonify({"ok": True})
    clear_app_cookie(response)
    if actor.role == "admin":
        clear_admin_cookie(response)
    return response

def register_routes(app) -> None:
    app.add_url_rule("/api/session", view_func=api_session, methods=["GET"])
    app.add_url_rule("/api/session/validate", view_func=api_session_validate, methods=["GET"])
    app.add_url_rule("/api/auth/verification/status", view_func=api_verification_status, methods=["POST"])
    app.add_url_rule("/api/auth/resend-confirmation", view_func=api_resend_confirmation, methods=["POST"])
    app.add_url_rule("/api/auth/change-email", view_func=api_change_email, methods=["POST"])
    app.add_url_rule("/api/auth/logout", view_func=api_logout, methods=["POST"])
