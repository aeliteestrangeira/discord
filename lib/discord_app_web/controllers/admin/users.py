from __future__ import annotations
from typing import Any
from flask import abort, redirect, render_template, request, url_for
from lib.discord_app.security import sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app.validators import ValidationError, validate_password_strength
from lib.discord_app_web.runtime import provider, session_authority
from lib.discord_app_web.security import admin_csrf_token, admin_identity, admin_required, audit, require_admin_csrf

def normalize_users(response: Any) -> list[dict[str, str]]:
    raw_users = getattr(response, "users", None)
    if raw_users is None:
        raw_users = response if isinstance(response, list) else []
    users: list[dict[str, str]] = []
    for user in raw_users:
        users.append({
            "id": str(getattr(user, "id", "") or ""),
            "email": str(getattr(user, "email", "") or ""),
            "phone": str(getattr(user, "phone", "") or ""),
            "created_at": str(getattr(user, "created_at", "") or ""),
            "last_sign_in_at": str(getattr(user, "last_sign_in_at", "") or ""),
            "email_confirmed_at": str(getattr(user, "email_confirmed_at", "") or ""),
            "banned_until": str(getattr(user, "banned_until", "") or ""),
        })
    return users

def admin_users():
    _, username = admin_identity()
    message = None
    error = None
    if request.method == "POST":
        require_admin_csrf()
        action = request.form.get("action", "")
        if action == "create":
            email = (request.form.get("email") or "").strip().lower()
            password = request.form.get("password") or ""
            email_confirm = request.form.get("email_confirm") == "1"
            if not email or "@" not in email or len(email) > 320 or not password or len(password) > 4096:
                error = "Dados do novo usuário são inválidos."
            else:
                try:
                    result = provider.create_user(email, password, email_confirm)
                    created = getattr(result, "user", result)
                    created_id = str(getattr(created, "id", "") or "")
                    audit("admin", username, "user.create", "success", target=created_id or sha256_text(email))
                    message = "Usuário criado."
                except ProviderError as exc:
                    audit("admin", username, "user.create", "denied", details={"provider_code": exc.code})
                    error = exc.public_message
                except Exception as exc:
                    audit("admin", username, "user.create", "failure", details={"error_type": exc.__class__.__name__})
                    error = "Falha ao criar usuário."
        elif action == "invite":
            email = (request.form.get("email") or "").strip().lower()
            if not email or "@" not in email or len(email) > 320:
                error = "E-mail de convite inválido."
            else:
                try:
                    provider.invite_user(email)
                    audit("admin", username, "user.invite", "success", target=sha256_text(email))
                    message = "Convite solicitado."
                except ProviderError as exc:
                    audit("admin", username, "user.invite", "denied", details={"provider_code": exc.code})
                    error = exc.public_message
                except Exception as exc:
                    audit("admin", username, "user.invite", "failure", details={"error_type": exc.__class__.__name__})
                    error = "Falha ao enviar convite."
        else:
            abort(400)

    users: list[dict[str, str]] = []
    if provider.admin_configured:
        try:
            users = normalize_users(provider.list_users(page=1, per_page=100))
            audit("admin", username, "user.list", "success", details={"count": len(users)})
        except Exception as exc:
            audit("admin", username, "user.list", "failure", details={"error_type": exc.__class__.__name__})
            error = error or "Não foi possível consultar os usuários."

    return render_template(
        "admin/users.html",
        username=username,
        csrf=admin_csrf_token(),
        users=users,
        admin_configured=provider.admin_configured,
        message=message,
        error=error,
    )

def admin_user_update(user_id: str):
    require_admin_csrf()
    _, username = admin_identity()
    action = request.form.get("action", "")
    attributes: dict[str, Any] = {}
    if action == "confirm-email":
        attributes["email_confirm"] = True
    elif action == "ban":
        attributes["ban_duration"] = "876000h"
    elif action == "unban":
        attributes["ban_duration"] = "none"
    elif action == "set-password":
        try:
            password = validate_password_strength(request.form.get("password"), field="Senha")
        except ValidationError:
            abort(400)
        attributes["password"] = password
    elif action == "set-email":
        email = (request.form.get("email") or "").strip().lower()
        if not email or "@" not in email or len(email) > 320:
            abort(400)
        attributes["email"] = email
    else:
        abort(400)
    try:
        provider.update_user(user_id, attributes)
        audit("admin", username, f"user.{action}", "success", target=user_id)
    except ProviderError as exc:
        audit("admin", username, f"user.{action}", "denied", target=user_id, details={"provider_code": exc.code})
    except Exception as exc:
        audit("admin", username, f"user.{action}", "failure", target=user_id, details={"error_type": exc.__class__.__name__})
    return redirect(url_for("admin_users"))

def admin_user_delete(user_id: str):
    require_admin_csrf()
    _, username = admin_identity()
    mode = request.form.get("mode", "hard")
    required = "DESATIVAR" if mode == "soft" else "EXCLUIR"
    if request.form.get("confirm") != required:
        audit("admin", username, "user.delete", "denied", target=user_id, details={"reason": "confirmation", "mode": mode})
        return redirect(url_for("admin_users"))
    try:
        provider.delete_user(user_id, soft=(mode == "soft"))
        revoked = session_authority.revoke_user(user_id)
        audit("admin", username, "user.delete", "success", target=user_id, details={"mode": mode, "local_sessions_revoked": revoked})
    except ProviderError as exc:
        audit("admin", username, "user.delete", "denied", target=user_id, details={"provider_code": exc.code})
    except Exception as exc:
        audit("admin", username, "user.delete", "failure", target=user_id, details={"error_type": exc.__class__.__name__})
    return redirect(url_for("admin_users"))


def register_routes(app) -> None:
    app.add_url_rule("/admin/users", view_func=admin_required(admin_users), methods=["GET", "POST"])
    app.add_url_rule("/admin/users/<user_id>/update", view_func=admin_required(admin_user_update), methods=["POST"])
    app.add_url_rule("/admin/users/<user_id>/delete", view_func=admin_required(admin_user_delete), methods=["POST"])
