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

def api_csrf():
    existing = request.cookies.get(APP_COOKIE, "")
    presence = request.cookies.get(APP_PRESENCE_COOKIE, "")
    reusable = False
    if existing and presence and constant_equal(presence, keys.presence_for_session(existing)):
        reusable = store.get_browser_session(existing) is not None
    if existing and not reusable:
        store.delete_browser_session(existing)
    raw, _ = store.ensure_browser_session(existing if reusable else None)
    response = jsonify({"csrfToken": keys.csrf_for_session(raw)})
    # Always synchronize the companion cookie. It carries no authentication
    # authority but is required as a second server-generated session token.
    set_app_cookie(response, raw)
    return response

def api_hcaptcha_config():
    return jsonify({
        "configured": captcha.configured,
        "required": True,
        "sitekey": captcha.sitekey if captcha.configured else "",
        "localHostname": APP_HOSTNAME,
    })

def register_routes(app) -> None:
    app.add_url_rule("/api/csrf", view_func=api_csrf, methods=["GET"])
    app.add_url_rule("/api/security/hcaptcha", view_func=api_hcaptcha_config, methods=["GET"])
