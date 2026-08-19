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

def api_passkey_options():
    require_browser_csrf()
    rate_bucket = f"passkey-options:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(rate_bucket, limit=30, window_seconds=300):
        audit("anonymous", None, "auth.passkey.options", "rate_limited", target="supabase-auth")
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas. Aguarde antes de tentar novamente."}}), 429
    try:
        result = provider.start_passkey_authentication()
    except ProviderError as exc:
        audit("anonymous", None, "auth.passkey.options", "denied", target="supabase-auth", details={"provider_code": exc.code})
        status = 503 if exc.code in {"not_configured", "passkey_disabled"} else 502
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    options = result.get("options") if isinstance(result.get("options"), dict) else None
    challenge_id = str(result.get("challenge_id") or "")
    if not options or not challenge_id:
        audit("anonymous", None, "auth.passkey.options", "failure", target="supabase-auth", details={"reason": "malformed_provider_response"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "passkey_options_invalid", "message": "Opções de chave de acesso inválidas."}}), 502
    audit("anonymous", None, "auth.passkey.options", "success", target="supabase-auth")
    return jsonify({"configured": True, "ok": True, "challengeId": challenge_id, "options": options, "expiresAt": result.get("expires_at")})

def api_passkey_verify():
    raw, _ = require_browser_csrf()
    payload = request.get_json(silent=True) or {}
    challenge_id = str(payload.get("challengeId") or "").strip()
    credential = payload.get("credential")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", challenge_id) or not isinstance(credential, dict):
        audit("anonymous", None, "auth.passkey.verify", "rejected", target="supabase-auth", details={"reason": "validation"})
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "validation", "message": "Resposta de chave de acesso inválida."}}), 400
    rate_bucket = f"passkey-verify:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(rate_bucket, limit=15, window_seconds=300):
        audit("anonymous", None, "auth.passkey.verify", "rate_limited", target="supabase-auth")
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas. Aguarde antes de tentar novamente."}}), 429
    try:
        result = provider.verify_passkey_authentication(challenge_id, credential)
    except ProviderError as exc:
        audit("anonymous", None, "auth.passkey.verify", "denied", target="supabase-auth", details={"provider_code": exc.code})
        status = 503 if exc.code in {"not_configured", "passkey_disabled"} else 401
        return jsonify({"configured": provider.public_configured, "ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    user_id = result.get("user_id") or ""
    if not user_id or not result.get("has_session"):
        audit("anonymous", None, "auth.passkey.verify", "failure", target="supabase-auth", details={"reason": "session_missing"})
        return jsonify({"configured": True, "ok": False, "error": {"code": "passkey_session_missing", "message": "A autenticação por chave de acesso não criou uma sessão válida."}}), 502
    new_raw = store.authenticate_browser_session(
        old_raw=raw,
        user_id=user_id,
        email=result.get("email") or "",
        access_token=result.get("access_token"),
        refresh_token=result.get("refresh_token"),
        expires_at_epoch=result.get("expires_at"),
        role="user",
        username=result.get("username") or "",
        global_name=result.get("global_name") or "",
        email_confirmed=bool(result.get("email_confirmed", True)),
    )
    existing_admin_raw = request.cookies.get(ADMIN_COOKIE, "")
    if existing_admin_raw:
        store.delete_admin_session(existing_admin_raw)
    audit("user", user_id, "auth.passkey.verify", "success", target="supabase-auth")
    response = jsonify({
        "configured": True,
        "ok": True,
        "status": "authenticated",
        "role": "user",
        "redirect": "/channels/@me",
        "csrfToken": keys.csrf_for_session(new_raw),
        "user": {
            "id": user_id,
            "email": result.get("email") or "",
            "phone": result.get("phone") or "",
            "username": result.get("username") or "",
            "globalName": result.get("global_name") or "",
            "emailConfirmed": bool(result.get("email_confirmed", True)),
        },
    })
    set_app_cookie(response, new_raw)
    if existing_admin_raw:
        clear_admin_cookie(response)
    return response

def register_routes(app) -> None:
    app.add_url_rule("/api/auth/passkey/options", view_func=api_passkey_options, methods=["POST"])
    app.add_url_rule("/api/auth/passkey/verify", view_func=api_passkey_verify, methods=["POST"])
