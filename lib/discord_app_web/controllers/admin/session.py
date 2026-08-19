from flask import redirect, render_template, request, url_for
from lib.discord_app_web.security import admin_required
from lib.discord_app_web.runtime import APP_COOKIE, captcha, cloudinary, gmail, provider, store
from lib.discord_app_web.security import admin_csrf_token, admin_identity, audit, clear_admin_cookie, clear_app_cookie, require_admin_csrf

def admin_logout():
    require_admin_csrf()
    _, username = admin_identity()
    admin_raw = getattr(request, "admin_sid", "")
    app_raw = request.cookies.get(APP_COOKIE, "")
    store.delete_admin_session(admin_raw)
    store.delete_browser_session(app_raw)
    audit("admin", username, "admin.logout", "success")
    response = redirect(url_for("home"))
    clear_admin_cookie(response)
    clear_app_cookie(response)
    return response

def admin_dashboard():
    _, username = admin_identity()
    chain_ok, chain_bad_id = store.verify_audit_chain()
    return render_template(
        "admin/dashboard.html",
        username=username,
        csrf=admin_csrf_token(),
        public_configured=provider.public_configured,
        admin_configured=provider.admin_configured,
        admin_key_kind=provider.admin_key_kind,
        database_configured=provider.database_configured,
        jwks_configured=bool(provider.jwks_url and provider.jwks_kid),
        hcaptcha_configured=captcha.configured,
        gmail_configured=gmail.configured,
        cloudinary_configured=cloudinary.configured,
        gmail_active_provider=gmail.active_provider,
        audit_chain_ok=chain_ok,
        audit_chain_bad_id=chain_bad_id,
        recent=store.list_audit(20),
    )


def register_routes(app) -> None:
    app.add_url_rule("/admin/logout", view_func=admin_required(admin_logout), methods=["POST"])
    app.add_url_rule("/admin", view_func=admin_required(admin_dashboard), methods=["GET"])
