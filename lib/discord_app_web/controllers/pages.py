from flask import current_app, jsonify, redirect, send_from_directory, url_for
from lib.discord_app_web.runtime import STATIC_PAGES_DIR


def home():
    return send_from_directory(STATIC_PAGES_DIR, "login.html")


def login_page_legacy():
    return redirect(url_for("home"), code=302)


def login_page_alias():
    return redirect(url_for("home"), code=302)


def register_page():
    return send_from_directory(STATIC_PAGES_DIR, "register.html")


def desktop_health():
    marker = str(current_app.config.get("DESKTOP_INSTANCE_MARKER", "") or "")
    return jsonify(ok=True, service="discord-local", marker=marker)


def register_routes(app) -> None:
    app.add_url_rule("/", view_func=home, methods=["GET"])
    app.add_url_rule("/login.html", view_func=login_page_legacy, methods=["GET"])
    app.add_url_rule("/login", view_func=login_page_alias, methods=["GET"])
    app.add_url_rule("/register.html", view_func=register_page, methods=["GET"])
    app.add_url_rule("/api/desktop/health", view_func=desktop_health, methods=["GET"])
