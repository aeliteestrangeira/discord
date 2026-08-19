from flask import abort, jsonify, request
from lib.discord_app.access import Actor, Policy
from lib.discord_app.security import sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.runtime import VOICE_ICE_SERVERS, provider, store
from lib.discord_app_web.security import audit, require_browser_csrf

def _voice_actor_from_csrf() -> Actor:
    _, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "voice.connect"):
        abort(403)
    return actor

def api_voice_join():
    actor = _voice_actor_from_csrf()
    payload = request.get_json(silent=True) or {}
    guild_id = str(payload.get("guildId") or "").strip()
    channel_id = str(payload.get("channelId") or "").strip()
    bucket = f"voice-join:{sha256_text(actor.id)}:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=30, window_seconds=60):
        audit("user", actor.id, "voice.join", "rate_limited", target=channel_id)
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitas tentativas de conexão de voz."}}), 429
    try:
        result = provider.voice_join(actor.id, guild_id, channel_id)
    except ProviderError as exc:
        audit("user", actor.id, "voice.join", "denied", target=channel_id, details={"provider_code": exc.code})
        status = 404 if exc.code in {"voice_channel_not_found", "guild_not_found"} else 400 if exc.code in {"voice_invalid", "voice_session_invalid"} else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    audit("user", actor.id, "voice.join", "success", target=channel_id, details={"voice_session": sha256_text(str(result.get("sessionId") or ""))[:16]})
    return jsonify({"ok": True, **result, "iceServers": VOICE_ICE_SERVERS})

def api_voice_state():
    actor = _voice_actor_from_csrf()
    payload = request.get_json(silent=True) or {}
    voice_session_id = str(payload.get("voiceSessionId") or "").strip()
    bucket = f"voice-state:{sha256_text(actor.id)}:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=180, window_seconds=60):
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Atualizações de voz excederam o limite."}}), 429
    try:
        result = provider.voice_state(actor.id, voice_session_id)
    except ProviderError as exc:
        status = 400 if exc.code == "voice_session_invalid" else 410 if exc.code == "voice_session_expired" else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    return jsonify({"ok": True, **result})

def api_voice_signal():
    actor = _voice_actor_from_csrf()
    payload = request.get_json(silent=True) or {}
    voice_session_id = str(payload.get("voiceSessionId") or "").strip()
    target_session_id = str(payload.get("targetSessionId") or "").strip()
    signal_type = str(payload.get("type") or "").strip().lower()
    signal_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    bucket = f"voice-signal:{sha256_text(actor.id)}:{request.remote_addr or 'unknown'}"
    if not store.allow_rate(bucket, limit=600, window_seconds=60):
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Sinalização de voz excedeu o limite."}}), 429
    try:
        provider.voice_signal(actor.id, voice_session_id, target_session_id, signal_type, signal_payload)
    except ProviderError as exc:
        status = 400 if exc.code in {"voice_session_invalid", "voice_signal_invalid", "voice_signal_too_large", "voice_target_invalid"} else 409 if exc.code == "voice_target_unavailable" else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    return jsonify({"ok": True})

def api_voice_leave():
    actor = _voice_actor_from_csrf()
    payload = request.get_json(silent=True) or {}
    voice_session_id = str(payload.get("voiceSessionId") or "").strip()
    try:
        provider.voice_leave(actor.id, voice_session_id)
    except ProviderError as exc:
        status = 400 if exc.code == "voice_session_invalid" else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status
    audit("user", actor.id, "voice.leave", "success", target=sha256_text(voice_session_id)[:16])
    return jsonify({"ok": True})


def register_routes(app) -> None:
    app.add_url_rule("/api/voice/join", view_func=api_voice_join, methods=["POST"])
    app.add_url_rule("/api/voice/state", view_func=api_voice_state, methods=["POST"])
    app.add_url_rule("/api/voice/signal", view_func=api_voice_signal, methods=["POST"])
    app.add_url_rule("/api/voice/leave", view_func=api_voice_leave, methods=["POST"])
