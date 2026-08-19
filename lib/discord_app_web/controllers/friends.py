from flask import abort, jsonify, request
from lib.discord_app.access import Actor, Policy
from lib.discord_app.hcaptcha_service import HCaptchaError
from lib.discord_app.security import sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.registration import registration_schema_ready
from lib.discord_app_web.runtime import captcha, provider, store
from lib.discord_app_web.security import audit, current_browser_session, require_browser_csrf, require_live_user_identity

def api_friend_request():
    raw, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "friend.request.create"):
        abort(403)

    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip().lower()
    captcha_token = str(payload.get("hcaptchaToken") or "").strip()
    if not username or len(username) > 37:
        return jsonify({"ok": False, "error": {"code": "friend_username_not_found", "message": "Hum, não funcionou. Confira se o nome de usuário está correto."}}), 404

    # Every friend-request attempt is human-verified before username lookup so
    # the endpoint cannot be used as a low-cost account-enumeration side channel.
    if not captcha.configured:
        audit("user", actor.id, "captcha.verify", "denied", target="hcaptcha", details={"reason": "not_configured", "flow": "friend-request"})
        return jsonify({"ok": False, "error": {"code": "captcha_not_configured", "message": "Verificação humana não configurada."}}), 503
    if not captcha_token:
        audit("user", actor.id, "captcha.verify", "denied", target="hcaptcha", details={"reason": "missing_token", "flow": "friend-request"})
        return jsonify({"ok": False, "error": {"code": "captcha_required", "message": "Confirme que você é humano."}}), 403
    try:
        captcha_result = captcha.verify(captcha_token, request.remote_addr)
    except HCaptchaError as exc:
        audit("user", actor.id, "captcha.verify", "failure", target="hcaptcha", details={"provider_code": exc.code, "flow": "friend-request"})
        return jsonify({"ok": False, "error": {"code": "captcha_unavailable", "message": exc.public_message}}), 503
    if not captcha_result.success:
        audit("user", actor.id, "captcha.verify", "denied", target="hcaptcha", details={"error_codes": list(captcha_result.error_codes), "hostname": captcha_result.hostname, "flow": "friend-request"})
        return jsonify({"ok": False, "error": {"code": "captcha_denied", "message": "A confirmação humana não foi aceita."}}), 403
    audit("user", actor.id, "captcha.verify", "success", target="hcaptcha", details={"hostname": captcha_result.hostname, "flow": "friend-request"})

    # Pending accounts get a tighter anti-abuse budget. Crossing it does not
    # silently lock the account: the client receives the captured
    # "Verification Required" flow and can resend/change the verification email.
    remote = request.remote_addr or "unknown"
    if actor.role == "pending":
        bucket = f"friend-request-pending:{sha256_text(actor.id)}:{remote}"
        if not store.allow_rate(bucket, limit=5, window_seconds=600):
            audit("user", actor.id, "friend.request.create", "rate_limited", target="verification-required")
            return jsonify({"ok": False, "error": {"code": "verification_required", "message": "Verifique seu e-mail para continuar enviando pedidos de amizade."}}), 429
    else:
        bucket = f"friend-request:{sha256_text(actor.id)}:{remote}"
        if not store.allow_rate(bucket, limit=20, window_seconds=600):
            audit("user", actor.id, "friend.request.create", "rate_limited", target="friend-requests")
            return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitos pedidos de amizade. Aguarde um pouco e tente novamente."}}), 429

    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "friend.request.create", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "Pedidos de amizade temporariamente indisponíveis."}}), 503
    try:
        result = provider.create_friend_request(actor.id, username)
    except ProviderError as exc:
        outcome = "not_found" if exc.code == "friend_username_not_found" else "denied"
        audit("user", actor.id, "friend.request.create", outcome, target="friend-requests", details={"provider_code": exc.code})
        status = 404 if exc.code in {"friend_username_not_found", "friend_self_not_allowed", "friend_request_conflict"} else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status

    audit("user", actor.id, "friend.request.create", "success", target="friend-requests", details={"receiver_id": result.get("receiver_id"), "status": "pending"})
    return jsonify({"ok": True, "request": {"id": result.get("request_id"), "status": "pending", "username": result.get("username")}})

def api_pending_friend_requests():
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "friend.request.read"):
        abort(403)
    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "friend.request.list", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "Pedidos de amizade temporariamente indisponíveis."}}), 503
    try:
        requests = provider.list_pending_friend_requests(actor.id)
    except ProviderError as exc:
        audit("user", actor.id, "friend.request.list", "failure", target="friend-requests", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), 503
    sent = requests.get("sent", [])
    received = requests.get("received", [])
    audit(
        "user", actor.id, "friend.request.list", "success", target="friend-requests",
        details={"sent_count": len(sent), "received_count": len(received)},
    )
    return jsonify({
        "ok": True,
        "sent": sent,
        "received": received,
        "sentCount": len(sent),
        "receivedCount": len(received),
        "count": len(sent) + len(received),
    })

def api_cancel_friend_request(request_id: str):
    _, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "friend.request.cancel"):
        abort(403)
    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "friend.request.cancel", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "Pedidos de amizade temporariamente indisponíveis."}}), 503
    try:
        result = provider.cancel_outgoing_friend_request(actor.id, request_id)
    except ProviderError as exc:
        status = 404 if exc.code == "friend_request_not_found" else 503
        audit("user", actor.id, "friend.request.cancel", "not_found" if status == 404 else "failure", target="friend-requests", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    audit("user", actor.id, "friend.request.cancel", "success", target="friend-requests", details={"receiver_id": result.get("receiver_id"), "deleted": True})
    return jsonify({"ok": True, "request": {"id": result.get("request_id"), "status": result.get("status")}})

def api_accept_friend_request(request_id: str):
    _, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "friend.request.accept"):
        abort(403)
    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "friend.request.accept", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "Pedidos de amizade temporariamente indisponíveis."}}), 503
    try:
        result = provider.accept_incoming_friend_request(actor.id, request_id)
    except ProviderError as exc:
        status = 404 if exc.code == "friend_request_not_found" else 503
        audit("user", actor.id, "friend.request.accept", "not_found" if status == 404 else "failure", target="friend-requests", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    audit("user", actor.id, "friend.request.accept", "success", target="friend-requests", details={"sender_id": result.get("sender_id")})
    return jsonify({"ok": True, "request": {"id": result.get("request_id"), "status": result.get("status")}})

def api_ignore_friend_request(request_id: str):
    _, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "friend.request.ignore"):
        abort(403)
    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "friend.request.ignore", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "Pedidos de amizade temporariamente indisponíveis."}}), 503
    try:
        result = provider.ignore_incoming_friend_request(actor.id, request_id)
    except ProviderError as exc:
        status = 404 if exc.code == "friend_request_not_found" else 503
        audit("user", actor.id, "friend.request.ignore", "not_found" if status == 404 else "failure", target="friend-requests", details={"provider_code": exc.code})
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    audit("user", actor.id, "friend.request.ignore", "success", target="friend-requests", details={"sender_id": result.get("sender_id"), "deleted": True})
    return jsonify({"ok": True, "request": {"id": result.get("request_id"), "status": result.get("status")}})


def register_routes(app) -> None:
    app.add_url_rule("/api/friends/requests", view_func=api_friend_request, methods=["POST"])
    app.add_url_rule("/api/friends/requests/pending", view_func=api_pending_friend_requests, methods=["GET"])
    app.add_url_rule("/api/friends/requests/<request_id>/cancel", view_func=api_cancel_friend_request, methods=["POST"])
    app.add_url_rule("/api/friends/requests/<request_id>/accept", view_func=api_accept_friend_request, methods=["POST"])
    app.add_url_rule("/api/friends/requests/<request_id>/ignore", view_func=api_ignore_friend_request, methods=["POST"])
