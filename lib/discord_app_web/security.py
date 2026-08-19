from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import abort, jsonify, redirect, request, url_for

from lib.discord_app.access import Actor, Policy
from lib.discord_app.security import constant_equal, is_loopback
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.runtime import (
    ADMIN_COOKIE, ADMIN_LOCAL_ONLY, ALLOWED_HOSTS, APP_COOKIE, APP_PRESENCE_COOKIE, COOKIE_SECURE,
    AUTH_SURFACE_PATHS, SENSITIVE_AUTH_QUERY_KEYS, keys, session_authority, store,
)

class BrowserSessionRevoked(RuntimeError):
    pass

class BrowserSessionValidationUnavailable(RuntimeError):
    pass


def _request_hostname() -> str:
    host = (request.host or "").strip()
    if host.startswith("["):
        end = host.find("]")
        return host[1:end].lower().rstrip(".") if end > 1 else ""
    if ":" in host:
        name, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            host = name
    return host.lower().rstrip(".")

def audit(
    actor_type: str,
    actor_id: str | None,
    action: str,
    outcome: str,
    target: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    store.add_audit(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        outcome=outcome,
        target=target,
        remote_addr=request.remote_addr if request else None,
        details=details or {},
    )

def set_app_cookie(response, raw: str):
    # Authentication remains in the HttpOnly opaque cookie. A second,
    # non-secret HMAC-bound presence cookie is intentionally readable by our
    # same-origin session controller so browser cookie deletion is observable
    # immediately instead of waiting for an authenticated request to fail.
    response.set_cookie(
        APP_COOKIE,
        raw,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Strict",
        path="/",
    )
    response.set_cookie(
        APP_PRESENCE_COOKIE,
        keys.presence_for_session(raw),
        max_age=12 * 60 * 60,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="Strict",
        path="/",
    )
    return response

def clear_app_cookie(response):
    response.delete_cookie(APP_COOKIE, path="/")
    response.delete_cookie(APP_PRESENCE_COOKIE, path="/")
    return response

def set_admin_cookie(response, raw: str):
    response.set_cookie(
        ADMIN_COOKIE,
        raw,
        max_age=8 * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Strict",
        path="/admin",
    )
    return response

def clear_admin_cookie(response):
    response.delete_cookie(ADMIN_COOKIE, path="/admin")
    return response

def require_same_origin() -> None:
    origin = request.headers.get("Origin")
    if not origin:
        return
    expected = request.host_url.rstrip("/")
    if origin.rstrip("/") != expected:
        abort(403)

def current_browser_session():
    raw = request.cookies.get(APP_COOKIE, "")
    if not raw:
        return "", None
    presence = request.cookies.get(APP_PRESENCE_COOKIE, "")
    expected = keys.presence_for_session(raw)
    if not presence or not constant_equal(presence, expected):
        # Session-fixation mitigation: the extra server-generated token
        # is mandatory on every authenticated browser session. Missing/tampered
        # companion state is a hard session break, never a signal to recreate it.
        store.delete_browser_session(raw)
        return "", None
    return raw, store.get_browser_session(raw)

def require_live_user_identity(raw: str, row: Any) -> Any:
    """Keep a local browser session subordinate to the real Auth principal.

    User/pending sessions are revoked when the matching ``auth.users`` row no
    longer exists (including soft deletion). Admin and anonymous sessions are
    intentionally outside this Supabase check.
    """
    actor = Actor.from_browser_session(row)
    if actor.role not in {"user", "pending"}:
        return row
    try:
        exists = session_authority.user_exists(actor.id)
    except ProviderError as exc:
        # Default deny: an authenticated shell is not allowed to keep operating
        # when its identity authority cannot be consulted. Revoke only the local
        # browser session; provider state is untouched.
        store.delete_browser_session(raw)
        audit("user", actor.id, "session.validate", "failure", target="supabase-auth", details={"provider_code": exc.code})
        raise BrowserSessionValidationUnavailable() from exc
    if not exists:
        revoked = session_authority.revoke_user(actor.id)
        audit("user", actor.id, "session.validate", "revoked", target="supabase-auth", details={"reason": "user_missing", "local_sessions_revoked": revoked})
        raise BrowserSessionRevoked()
    return row

def require_browser_csrf() -> tuple[str, Any]:
    require_same_origin()
    raw, row = current_browser_session()
    if not raw or not row:
        abort(403)
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = keys.csrf_for_session(raw)
    if not supplied or not constant_equal(supplied, expected):
        abort(403)
    row = require_live_user_identity(raw, row)
    return raw, row

def current_admin_session():
    raw = request.cookies.get(ADMIN_COOKIE, "")
    row = store.get_admin_session(raw)
    return raw, row

def admin_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if store.admin_count() == 0:
            return "Administrador local não instalado.", 503
        raw, row = current_admin_session()
        _, browser_row = current_browser_session()
        actor = Actor.from_browser_session(browser_row)
        if raw and row:
            expected_user_id = f"local-admin:{int(row['admin_id'])}"
            # Authorization requires both independently stored sessions to agree
            # on the privileged principal. The actor is resolved only from the
            # trusted server-side browser session; browser payload cannot choose
            # role/authority. A stale admin cookie cannot elevate another actor.
            if not Policy.allowed(actor, "admin.access") or actor.id != expected_user_id:
                store.delete_admin_session(raw)
                abort(403)
            request.admin_session = row  # type: ignore[attr-defined]
            request.admin_sid = raw  # type: ignore[attr-defined]
            return view(*args, **kwargs)

        # The public login page is the only authentication entry point. An
        # already-authenticated non-admin principal receives a hard deny rather
        # than being redirected into an authentication loop.
        if browser_row and browser_row["user_id"]:
            if (browser_row["role"] or "user") != "admin":
                abort(403)
        return redirect(url_for("home"))
    return wrapped

def admin_csrf_token() -> str:
    raw = getattr(request, "admin_sid", "") or request.cookies.get(ADMIN_COOKIE, "")
    return keys.csrf_for_session(raw) if raw else ""

def require_admin_csrf() -> None:
    """Require an authenticated admin-session CSRF token.

    The administrator is loopback-only by default and the session cookie is
    SameSite=Strict.  The synchronizer token is still mandatory for every
    state-changing administrator request.  We intentionally do not make the
    browser Origin header an authorization dependency here: privacy-focused
    browsers and local proxy stacks can omit or rewrite Origin on loopback
    form submissions.  Authorization continues to fail closed on an invalid
    session or token.
    """
    expected = admin_csrf_token()
    supplied = request.form.get("_csrf", "") or request.headers.get("X-CSRF-Token", "")
    if not expected or not supplied or not constant_equal(supplied, expected):
        row = getattr(request, "admin_session", None)
        username = str(row["username"]) if row and row["username"] else None
        reason = "missing_expected" if not expected else "missing_supplied" if not supplied else "token_mismatch"
        audit(
            "admin",
            username,
            "admin.csrf",
            "denied",
            target=request.path,
            details={"reason": reason, "method": request.method},
        )
        abort(403)

def admin_identity() -> tuple[int, str]:
    row = getattr(request, "admin_session", None)
    if not row:
        abort(401)
    return int(row["admin_id"]), str(row["username"])

def strip_auth_query_credentials():
    """Fail closed if an authentication form ever falls back to a native GET.

    The captured login/register HTML intentionally remains untouched. Both forms
    have no explicit method/action in the source capture, so a JavaScript boot
    failure would otherwise make the browser serialize credentials into the URL.
    Remove the query immediately and never reflect it into another redirect.
    """
    if request.method not in {"GET", "HEAD"} or request.path not in AUTH_SURFACE_PATHS:
        return None
    supplied = {str(key).lower() for key in request.args.keys()}
    if supplied & SENSITIVE_AUTH_QUERY_KEYS:
        return redirect(request.path, code=302)
    return None

def reject_untrusted_host():
    """Reject Host headers outside the explicit local/deployment allowlist.

    This closes DNS-rebinding/Host-header paths against a loopback-bound server.
    The browser origin is intentionally singular: ``APP_HOSTNAME=discord``.
    Requests carrying any other Host value are rejected before route handling.
    """
    host = _request_hostname()
    if not host or host not in ALLOWED_HOSTS:
        abort(400)

def default_deny_admin_remote():
    if request.path.startswith("/admin") and ADMIN_LOCAL_ONLY and not is_loopback(request.remote_addr):
        abort(403)

def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self), geolocation=(), payment=(), publickey-credentials-get=(self), publickey-credentials-create=(self)"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' data:; "
        "script-src 'self' https://hcaptcha.com https://*.hcaptcha.com; "
        "style-src 'self' 'unsafe-inline' https://hcaptcha.com https://*.hcaptcha.com; "
        "img-src 'self' data: https://res.cloudinary.com; "
        "media-src 'self' https://res.cloudinary.com; "
        "font-src 'self' data:; "
        "connect-src 'self' https://hcaptcha.com https://*.hcaptcha.com; "
        "frame-src https://hcaptcha.com https://*.hcaptcha.com; "
        "object-src 'none'; "
        "manifest-src 'self'; "
        "form-action 'self'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'"
    )
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.endswith((".html", ".js")) or request.path.startswith(("/api/", "/admin", "/channels")):
        response.headers["Cache-Control"] = "no-store"
    return response


def register_security_hooks(app) -> None:
    app.before_request(strip_auth_query_credentials)
    app.before_request(reject_untrusted_host)
    app.before_request(default_deny_admin_remote)
    app.after_request(security_headers)
