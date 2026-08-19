from flask import jsonify, redirect, request, url_for
from lib.discord_app_web.security import (
    BrowserSessionRevoked, BrowserSessionValidationUnavailable, clear_app_cookie,
)

def browser_session_revoked(_):
    if request.path.startswith("/api/"):
        response = jsonify({"ok": False, "authenticated": False, "error": {"code": "session_revoked", "message": "Esta conta não está mais disponível."}})
        response.status_code = 401
    else:
        response = redirect(url_for("home"), code=302)
    clear_app_cookie(response)
    return response

def browser_session_validation_unavailable(_):
    if request.path.startswith("/api/"):
        response = jsonify({"ok": False, "authenticated": False, "error": {"code": "session_validation_unavailable", "message": "Não foi possível validar a sessão agora."}})
        response.status_code = 503
    else:
        response = redirect(url_for("home"), code=302)
    clear_app_cookie(response)
    return response

def forbidden(_):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": {"code": "forbidden", "message": "Acesso negado."}}), 403
    return "Acesso negado.", 403

def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": {"code": "not_found", "message": "Recurso não encontrado."}}), 404
    return "Recurso não encontrado.", 404


def register_error_handlers(app) -> None:
    app.register_error_handler(BrowserSessionRevoked, browser_session_revoked)
    app.register_error_handler(BrowserSessionValidationUnavailable, browser_session_validation_unavailable)
    app.register_error_handler(403, forbidden)
    app.register_error_handler(404, not_found)
