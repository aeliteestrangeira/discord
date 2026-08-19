from __future__ import annotations

import json
import re
import secrets
from html import escape as html_escape
from typing import Any

from lib.discord_app.access import Actor

def _session_bootstrap_html(actor: Actor, row: Any) -> str:
    payload = json.dumps({
        "authenticated": True,
        "role": actor.role,
        "user": {
            "id": actor.id,
            "email": str(row["email"] or ""),
            "username": str(row["username"] or ""),
            "globalName": str(row["global_name"] or ""),
            "emailConfirmed": bool(row["email_confirmed"]),
        },
    }, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<script type="application/json" id="app-session-bootstrap">{payload}</script>'

def _friend_notification_badge_html(count: int, *, tab: bool = False, sidebar: bool = False) -> str:
    """Render only the captured Discord badge structure used by the authenticated shell."""
    value = max(0, int(count or 0))
    classes = ["eyebrow_cf4812"]
    if tab:
        classes.append("badge__133bf")
    classes.extend(["numberBadge__463b7", "base__463b7", "baseShapeRound__463b7"])
    marker = ' data-app-friend-incoming-badge="true"' if sidebar else ""
    width = "auto" if value > 9 else "16px"
    padding = " padding: 0 4px;" if value > 9 else ""
    # The captured tab badge uses the normal number-badge classes, but its text
    # can inherit tab line metrics differently at browser zoom levels. Keep the
    # original classes and make the 16px badge box explicit in the dynamic HTML
    # so the numeral is optically centered from the first server-rendered frame.
    tab_geometry = (
        " height: 16px; min-width: 16px; box-sizing: border-box; "
        "display: flex; align-items: center; justify-content: center; line-height: 16px;"
        if tab else ""
    )
    return (
        f'<div class="{" ".join(classes)}" data-text-variant="eyebrow"{marker} '
        f'style="background-color: var(--badge-notification-background); width: {width};{padding}{tab_geometry}">{value}</div>'
    )

def _friend_pending_bootstrap_html(requests: dict[str, Any], *, ready: bool = True) -> tuple[str, int, int]:
    sent = requests.get("sent") if isinstance(requests, dict) else []
    received = requests.get("received") if isinstance(requests, dict) else []
    sent = sent if isinstance(sent, list) else []
    received = received if isinstance(received, list) else []
    incoming = len(received)
    total = len(sent) + incoming
    payload = json.dumps(
        {"ready": bool(ready), "sent": sent, "received": received, "sentCount": len(sent), "receivedCount": incoming, "count": total},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # ``application/json`` is inert, but user profile fields can still contain
    # HTML-significant bytes. Escape them so no value can terminate the script
    # element before the frontend parses the JSON payload.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    return f'<script type="application/json" id="app-friend-pending-bootstrap">{payload}</script>', total, incoming

def _hydrate_friend_pending_shell(html: str, requests: dict[str, Any], *, ready: bool = True) -> tuple[str, str]:
    """Server-render friend notification chrome before the authenticated page is sent.

    ``channels.html`` remains the protected captured source. This function only
    projects current database state into the HTTP response so Pending/Friends
    badges never appear one asynchronous request after first paint.
    """
    bootstrap, total, incoming = _friend_pending_bootstrap_html(requests, ready=ready)
    if total > 0:
        tab_badge = _friend_notification_badge_html(incoming, tab=True) if incoming > 0 else ""
        aria = f'Pendentes, {incoming} novo' if incoming == 1 else (f'Pendentes, {incoming} novos' if incoming > 1 else 'Pendentes')
        pending_tab = (
            '<div class="item__133bf item_aa8da2 themed_aa8da2" data-app-pending-tab="true" '
            'role="tab" aria-selected="false" aria-disabled="false" tabindex="-1" '
            f'aria-label="{aria}" aria-controls="pending-tab">'
            '<div class="text-md/medium_cf4812 itemText_aa8da2" data-text-variant="text-md/medium">'
            f'Pendentes{tab_badge}</div></div>'
        )
        add_tab_at = html.find('<div class="item__133bf addFriend__133bf')
        if add_tab_at >= 0:
            html = html[:add_tab_at] + pending_tab + html[add_tab_at:]

    if incoming > 0:
        link_match = re.search(
            r'<a class="link__972a0"[^>]*data-list-item-id="[^"]*___friends"[^>]*>',
            html,
        )
        if link_match:
            anchor_end = html.find("</a>", link_match.end())
            if anchor_end >= 0:
                html = html[:anchor_end] + _friend_notification_badge_html(incoming, sidebar=True) + html[anchor_end:]
    return html, bootstrap

def _guild_acronym(name: str) -> str:
    """Match the captured two-letter server tile fallback (e.g. "name's server" -> "ns")."""
    words = [part for part in re.split(r"\s+", (name or "").strip()) if part]
    letters: list[str] = []
    for word in words:
        match = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]", word)
        if match:
            letters.append(match.group(0).lower())
        if len(letters) >= 2:
            break
    if not letters:
        return "s"
    return "".join(letters[:2])

def _guild_sidebar_item_html(guild: dict[str, Any], *, selected: bool = False, position: int = 1, total: int = 1) -> str:
    guild_id = str(guild.get("id") or "")
    channel_id = str(guild.get("default_channel_id") or "")
    name = str(guild.get("name") or "Servidor")
    has_icon = bool(guild.get("has_icon"))
    icon_hash = str(guild.get("icon_sha256") or "")
    safe_id = html_escape(guild_id, quote=True)
    safe_channel = html_escape(channel_id, quote=True)
    safe_name = html_escape(name, quote=True)
    node_key = re.sub(r"[^A-Za-z0-9_-]", "", guild_id)[:24] or secrets.token_hex(4)
    selected_overlay = " visible__58105 selected__58105" if selected else ""
    selected_blob = " selected_e5445c" if selected else ""
    selected_wrapper = " selected__6e9f8" if selected else ""
    aria_selected = "true" if selected else "false"
    if has_icon:
        version = f"?v={html_escape(icon_hash, quote=True)}" if icon_hash else ""
        face = (
            f'<img class="icon__6e9f8" alt=" " width="40" height="40" aria-hidden="true" '
            f'src="/api/guilds/{safe_id}/icon{version}">'
        )
    else:
        face = (
            '<div class="childWrapper__6e9f8 childWrapperNoHoverBg__6e9f8 acronym__6e9f8" '
            f'aria-hidden="true">{html_escape(_guild_acronym(name))}</div>'
        )
    blob_path = (
        "M0 17.4545C0 11.3449 0 8.29005 1.18902 5.95647C2.23491 3.90379 "
        "3.90379 2.23491 5.95647 1.18902C8.29005 0 11.3449 0 17.4545 0H22.5455C28.6551 0 "
        "31.71 0 34.0435 1.18902C36.0962 2.23491 37.7651 3.90379 38.811 5.95647C40 8.29005 40 "
        "11.3449 40 17.4545V22.5455C40 28.6551 40 31.71 38.811 34.0435C37.7651 36.0962 36.0962 "
        "37.7651 34.0435 38.811C31.71 40 28.6551 40 22.5455 40H17.4545C11.3449 40 8.29005 40 "
        "5.95647 38.811C3.90379 37.7651 2.23491 36.0962 1.18902 34.0435C0 31.71 0 28.6551 0 "
        "22.5455V17.4545Z"
    )
    outer_blob = f"app-guild-{node_key}-outer-blob"
    outer_mask = f"app-guild-{node_key}-outer-mask"
    inner_blob = f"app-guild-{node_key}-inner-blob"
    inner_mask = f"app-guild-{node_key}-inner-mask"
    return (
        '<div class="listItem__650eb">'
          '<div class="wrapper__58105 overlay__58105" aria-hidden="true">'
            f'<span class="item__58105{selected_overlay}"></span>'
          '</div><span>'
            f'<div class="blobContainer_e5445c{selected_blob}" data-drop-hovering="false" style="transform: none;">'
              '<div class="wrapper_cc5dd2" style="width: 40px; height: 40px;">'
                '<svg width="48" height="48" viewBox="-4 -4 48 48" class="svg_cc5dd2 shiftSVG_cc5dd2" overflow="visible" role="none">'
                  f'<defs><path d="{blob_path}" id="{outer_blob}"></path></defs>'
                  f'<mask id="{outer_mask}" fill="black" x="0" y="0" width="40" height="40"><use href="#{outer_blob}" fill="white"></use></mask>'
                  f'<foreignObject mask="url(#{outer_mask})" x="0" y="0" width="40" height="40">'
                    '<div class="wrapper_cc5dd2" style="width: 40px; height: 40px;">'
                      '<svg width="48" height="48" viewBox="-4 -4 48 48" class="svg_cc5dd2 shiftSVG_cc5dd2" overflow="visible" role="none">'
                        f'<defs><path d="{blob_path}" id="{inner_blob}"></path></defs>'
                        f'<mask id="{inner_mask}" fill="black" x="0" y="0" width="40" height="40"><use href="#{inner_blob}" fill="white"></use></mask>'
                        f'<foreignObject mask="url(#{inner_mask})" x="0" y="0" width="40" height="40">'
                          f'<div data-app-guild-id="{safe_id}" data-app-guild-channel-id="{safe_channel}" data-dnd-name="{safe_name}" data-drop-hovering="false" draggable="false">'
                            f'<div class="wrapper__6e9f8{selected_wrapper}" role="treeitem" data-list-item-id="guildsnav___{safe_id}" tabindex="-1" aria-level="1" aria-setsize="{max(1,total)}" aria-posinset="{max(1,position)}" aria-selected="{aria_selected}" style="font-size: 18px;">'
                              f'<span class="hiddenVisually_b18fe2">{safe_name}</span>{face}'
                            '</div>'
                          '</div>'
                        '</foreignObject>'
                      '</svg>'
                    '</div>'
                  '</foreignObject>'
                '</svg>'
              '</div>'
            '</div>'
          '</span>'
          '<span class="hiddenVisually_b18fe2">'
            '<div class="text-md/semibold_cf4812 guildTooltipWrapper_b1f768" data-text-variant="text-md/semibold" style="color: var(--text-default);">'
              f'<div class="row_b1f768 rowGuildName_b1f768"><span class="guildNameText_b1f768 guildNameTextLimitedSize_b1f768">{safe_name}</span></div>'
            '</div>'
          '</span>'
          '<div class="wrapper_d144f8" aria-hidden="true">'
            f'<div data-dnd-name="Acima de {safe_name}" class="target_d144f8"></div>'
            f'<div data-dnd-name="Combinar com {safe_name}" class="centerTarget_d144f8"></div>'
          '</div>'
        '</div>'
    )

def _hydrate_guild_sidebar(html: str, guilds: list[dict[str, Any]], *, selected_guild_id: str = "") -> str:
    opening = '<div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" role="group" aria-label="Servidores" style="gap: var(--space-xs); padding: var(--space-0);">'
    start = html.find(opening)
    if start < 0:
        # The source template may retain the capture's English ARIA label.
        opening_en = opening.replace('aria-label="Servidores"', 'aria-label="Servers"')
        start = html.find(opening_en)
        if start < 0:
            return html
        opening = opening_en
    content_start = start + len(opening)
    marker = '<div class="tutorialContainer__650eb">'
    content_end = html.find(marker, content_start)
    if content_end < 0:
        return html
    total = len(guilds)
    items = "".join(
        _guild_sidebar_item_html(guild, selected=str(guild.get("id") or "") == selected_guild_id, position=index, total=total)
        for index, guild in enumerate(guilds, start=1)
    )
    return html[:content_start] + items + html[content_end:]

def _detect_guild_icon_media(data: bytes, declared: str = "") -> str | None:
    """Allow only raster formats accepted by the captured file input."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif data.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        detected = "image/gif"
    elif len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        detected = "image/webp"
    elif len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis"}:
        detected = "image/avif"
    else:
        return None
    declared = (declared or "").split(";", 1)[0].strip().lower()
    if declared and declared not in {detected, "image/jpg" if detected == "image/jpeg" else detected}:
        return None
    return detected
