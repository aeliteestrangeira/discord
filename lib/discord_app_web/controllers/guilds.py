from __future__ import annotations

import json
import time
from html import escape as html_escape
from typing import Any

from flask import abort, jsonify, make_response, redirect, request, send_from_directory, url_for

from lib.discord_app.access import Actor, Policy
from lib.discord_app.security import sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.presenters import (
    _detect_guild_icon_media, _guild_acronym, _hydrate_friend_pending_shell,
    _hydrate_guild_sidebar, _session_bootstrap_html,
)
from lib.discord_app_web.registration import registration_schema_ready
from lib.discord_app_web.runtime import STATIC_PAGES_DIR, provider, store
from lib.discord_app_web.security import (
    audit, clear_app_cookie, current_browser_session, require_browser_csrf,
    require_live_user_identity,
)

def channels_me_page():
    spa_partial = request.headers.get("X-App-SPA", "") == "1"
    timing_started = time.perf_counter()
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    identity_ms = (time.perf_counter() - timing_started) * 1000.0
    actor = Actor.from_browser_session(row)
    if actor.role == "admin" and Policy.allowed(actor, "admin.access"):
        return redirect(url_for("admin_dashboard"), code=302)
    if not actor.authenticated or not Policy.allowed(actor, "shell.read"):
        response = redirect(url_for("home"), code=302)
        clear_app_cookie(response)
        return response

    # A página autenticada mantém a estrutura/classes/estilos da captura, mas
    # o texto estático já está traduzido diretamente em channels.html. Nenhum
    # script de tradução é necessário; somente comportamento é anexado aqui.
    html = (STATIC_PAGES_DIR / "channels.html").read_text(encoding="utf-8")
    # Substitui somente o username placeholder na fronteira server-side para
    # evitar qualquer flash com o nome presente na captura original.
    username = str(row["username"] or "").strip().lower()
    if not username:
        email = str(row["email"] or "").strip().lower()
        username = email.split("@", 1)[0] if "@" in email else "usuário"
    html = html.replace("aeliteestrangeira", html_escape(username))
    if bool(row["email_confirmed"]) or actor.role == "user":
        captured_notice = (
            '<div class="notice__6e2b9 colorDefault__6e2b9">'
            'Verifique seu e-mail para confirmar sua conta e manter seu nome de usuário atual.'
            '<button class="button__6e2b9">Reenviar e-mail</button></div>'
        )
        html = html.replace(captured_notice, "", 1)
    # Load pending friend state before returning the document. The source capture
    # stays unchanged on disk, while the response already contains the Pending
    # tab/sidebar badge and an inert JSON snapshot for zero-flash hydration.
    friend_requests: dict[str, Any] = {"sent": [], "received": []}
    friend_bootstrap_ready = True
    friend_started = time.perf_counter()
    try:
        friend_requests = provider.list_pending_friend_requests(actor.id)
    except ProviderError:
        # Friend-request availability must not destroy an otherwise valid shell.
        # Mark this snapshot unavailable so the frontend performs its immediate
        # recovery fetch instead of treating an empty fallback as authoritative.
        friend_bootstrap_ready = False
    friend_ms = (time.perf_counter() - friend_started) * 1000.0
    html, friend_bootstrap = _hydrate_friend_pending_shell(html, friend_requests, ready=friend_bootstrap_ready)

    guild_started = time.perf_counter()
    guilds: list[dict[str, Any]] = []
    if not spa_partial:
        try:
            guilds = provider.list_user_guilds(actor.id)
        except ProviderError:
            guilds = []
        html = _hydrate_guild_sidebar(html, guilds)
    guild_ms = (time.perf_counter() - guild_started) * 1000.0
    session_bootstrap = _session_bootstrap_html(actor, row)

    loader = '<script src="/auth-provider.js"></script><script src="/ui.js"></script>'
    if "</body>" in html:
        html = html.replace("</body>", f"{session_bootstrap}{friend_bootstrap}{loader}</body>", 1)
    response = make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Server-Timing"] = f"session;dur={identity_ms:.2f}, friends;dur={friend_ms:.2f}, guilds;dur={guild_ms:.2f}"
    if spa_partial:
        response.headers["X-App-SPA"] = "1"
    return response

def api_create_guild():
    raw, row = require_browser_csrf()
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "guild.create"):
        abort(403)
    if not registration_schema_ready(repair=True):
        audit("user", actor.id, "guild.create", "denied", target="database", details={"reason": "schema_not_ready"})
        return jsonify({"ok": False, "error": {"code": "schema_not_ready", "message": "A criação de servidores está temporariamente indisponível."}}), 503

    name = str(request.form.get("name") or "").strip()
    template_key = str(request.form.get("templateKey") or "custom").strip().lower()
    audience = str(request.form.get("audience") or "friends").strip().lower()
    if not name or len(name) > 100:
        return jsonify({"ok": False, "error": {"code": "guild_name_invalid", "message": "O nome do servidor deve ter entre 1 e 100 caracteres."}}), 400

    remote = request.remote_addr or "unknown"
    bucket = f"guild-create:{sha256_text(actor.id)}:{remote}"
    if not store.allow_rate(bucket, limit=8, window_seconds=900):
        audit("user", actor.id, "guild.create", "rate_limited", target="guilds")
        return jsonify({"ok": False, "error": {"code": "rate_limited", "message": "Muitos servidores foram criados recentemente. Aguarde um pouco e tente novamente."}}), 429

    icon_bytes: bytes | None = None
    icon_media_type: str | None = None
    icon = request.files.get("icon")
    if icon and icon.filename:
        icon_bytes = icon.stream.read(8 * 1024 * 1024 + 1)
        if len(icon_bytes) > 8 * 1024 * 1024:
            return jsonify({"ok": False, "error": {"code": "guild_icon_too_large", "message": "A imagem do servidor é muito grande."}}), 413
        icon_media_type = _detect_guild_icon_media(icon_bytes, icon.mimetype or "")
        if not icon_media_type:
            return jsonify({"ok": False, "error": {"code": "guild_icon_invalid", "message": "Use uma imagem JPG, PNG, GIF, WEBP ou AVIF válida."}}), 400

    try:
        created = provider.create_guild(
            actor.id,
            name=name,
            template_key=template_key,
            audience=audience,
            icon_media_type=icon_media_type,
            icon_bytes=icon_bytes,
        )
    except ProviderError as exc:
        audit("user", actor.id, "guild.create", "denied", target="guilds", details={"provider_code": exc.code})
        status = 400 if exc.code in {"guild_name_invalid", "guild_template_invalid", "guild_audience_invalid", "guild_icon_invalid", "guild_icon_too_large"} else 503
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), status

    guild_id = str(created.get("guild_id") or "")
    channel_id = str(created.get("channel_id") or "")
    audit(
        "user", actor.id, "guild.create", "success", target=guild_id,
        details={
            "template_key": created.get("template_key"),
            "audience": created.get("audience"),
            "has_icon": bool(created.get("has_icon")),
            "icon_sha256": created.get("icon_sha256") or "",
            "default_channel_id": channel_id,
        },
    )
    return jsonify({
        "ok": True,
        "guild": {
            "id": guild_id,
            "name": created.get("name") or name,
            "defaultChannelId": channel_id,
            "defaultChannelName": created.get("channel_name") or "general",
            "hasIcon": bool(created.get("has_icon")),
        },
        "redirect": f"/channels/{guild_id}/{channel_id}",
    })

def api_guild_icon(guild_id: str):
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "guild.read"):
        abort(403)
    try:
        data, media_type, digest = provider.get_guild_icon_for_user(actor.id, guild_id)
    except ProviderError as exc:
        if exc.code == "guild_icon_not_found":
            abort(404)
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), 503
    response = make_response(data)
    response.headers["Content-Type"] = media_type
    response.headers["Content-Length"] = str(len(data))
    if digest:
        response.headers["ETag"] = f'"{digest}"'
    return response

def guild_default_page(guild_id: str):
    raw, row = current_browser_session()
    if row:
        row = require_live_user_identity(raw, row)
    actor = Actor.from_browser_session(row)
    if not actor.authenticated or not Policy.allowed(actor, "guild.read"):
        response = redirect(url_for("home"), code=302)
        clear_app_cookie(response)
        return response
    try:
        guilds = provider.list_user_guilds(actor.id)
    except ProviderError:
        abort(503)
    selected = next((g for g in guilds if str(g.get("id") or "") == guild_id), None)
    if not selected or not selected.get("default_channel_id"):
        abort(404)
    return redirect(f"/channels/{guild_id}/{selected['default_channel_id']}", code=302)

def guild_channel_page(guild_id: str, channel_id: str):
    spa_partial = request.headers.get("X-App-SPA", "") == "1"
    timing_started = time.perf_counter()
    raw, row = current_browser_session()
    # Full document loads independently validate the live principal. SPA guild
    # navigation validates the actor inside the guild membership query itself,
    # avoiding a second remote DB connection on every click.
    if row and not spa_partial:
        row = require_live_user_identity(raw, row)
    identity_ms = (time.perf_counter() - timing_started) * 1000.0
    actor = Actor.from_browser_session(row)
    if actor.role == "admin" and Policy.allowed(actor, "admin.access"):
        return redirect(url_for("admin_dashboard"), code=302)
    if not actor.authenticated or not Policy.allowed(actor, "guild.read"):
        response = redirect(url_for("home"), code=302)
        clear_app_cookie(response)
        return response

    guild_started = time.perf_counter()
    try:
        current, guild_channels = provider.get_guild_view_for_user(actor.id, guild_id, channel_id)
        guilds = [] if spa_partial else provider.list_user_guilds(actor.id)
    except ProviderError as exc:
        if exc.code == "guild_not_found":
            abort(404)
        abort(503)
    guild_ms = (time.perf_counter() - guild_started) * 1000.0

    html = (STATIC_PAGES_DIR / "guild.html").read_text(encoding="utf-8")
    username = str(row["username"] or "").strip().lower()
    if not username:
        email = str(row["email"] or "").strip().lower()
        username = email.split("@", 1)[0] if "@" in email else "usuário"
    replacements = {
        "__APP_GUILD_NAME__": html_escape(str(current.get("name") or "Servidor"), quote=True),
        "__APP_USERNAME__": html_escape(username, quote=True),
        "__APP_GUILD_ID__": html_escape(str(current.get("id") or guild_id), quote=True),
        "__APP_CHANNEL_ID__": html_escape(str(current.get("channel_id") or channel_id), quote=True),
        "__APP_GUILD_ACRONYM__": html_escape(_guild_acronym(str(current.get("name") or "Servidor"))),
    }
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    if not spa_partial:
        html = _hydrate_guild_sidebar(html, guilds, selected_guild_id=str(current.get("id") or guild_id))

    if bool(row["email_confirmed"]) or actor.role == "user":
        captured_notice = (
            '<div class="notice__6e2b9 colorDefault__6e2b9">'
            'Verifique seu e-mail para confirmar sua conta e manter seu nome de usuário atual.'
            '<button class="button__6e2b9">Reenviar e-mail</button></div>'
        )
        html = html.replace(captured_notice, "", 1)

    session_bootstrap = _session_bootstrap_html(actor, row)
    guild_payload = json.dumps({
        "id": str(current.get("id") or guild_id),
        "name": str(current.get("name") or "Servidor"),
        "channelId": str(current.get("channel_id") or channel_id),
        "channelName": str(current.get("channel_name") or "general"),
        "channelType": str(current.get("channel_type") or "text"),
        "ownerId": str(current.get("owner_id") or ""),
        "memberRole": str(current.get("member_role") or "member"),
        "channels": [{
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "type": str(item.get("channel_type") or "text"),
            "position": int(item.get("position") or 0),
        } for item in guild_channels],
    }, ensure_ascii=False, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    guild_bootstrap = f'<script type="application/json" id="app-guild-bootstrap">{guild_payload}</script>'
    loader = '<script src="/auth-provider.js"></script><script src="/ui.js"></script>'
    if "</body>" in html:
        html = html.replace("</body>", f"{session_bootstrap}{guild_bootstrap}{loader}</body>", 1)
    response = make_response(html)
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.headers["Server-Timing"] = f"session;dur={identity_ms:.2f}, guild;dur={guild_ms:.2f}"
    if spa_partial:
        response.headers["X-App-SPA"] = "1"
    return response


def register_routes(app) -> None:
    app.add_url_rule("/channels/@me", view_func=channels_me_page, methods=["GET"])
    app.add_url_rule("/api/guilds", view_func=api_create_guild, methods=["POST"])
    app.add_url_rule("/api/guilds/<guild_id>/icon", view_func=api_guild_icon, methods=["GET"])
    app.add_url_rule("/channels/<guild_id>", view_func=guild_default_page, methods=["GET"])
    app.add_url_rule("/channels/<guild_id>/<channel_id>", view_func=guild_channel_page, methods=["GET"])
