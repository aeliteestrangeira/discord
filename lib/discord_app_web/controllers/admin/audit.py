from flask import abort, render_template, request, send_from_directory
from lib.discord_app.security import is_loopback
from lib.discord_app_web.runtime import ADMIN_LOCAL_ONLY, ASSET_CSS_DIR, store
from lib.discord_app_web.security import admin_csrf_token, admin_identity, admin_required

def admin_audit():
    _, username = admin_identity()
    chain_ok, chain_bad_id = store.verify_audit_chain()
    rows = store.list_audit(500)
    return render_template(
        "admin/audit.html",
        username=username,
        csrf=admin_csrf_token(),
        rows=rows,
        chain_ok=chain_ok,
        chain_bad_id=chain_bad_id,
    )

def admin_css():
    if ADMIN_LOCAL_ONLY and not is_loopback(request.remote_addr):
        abort(403)
    return send_from_directory(ASSET_CSS_DIR, "admin.css")


def register_routes(app) -> None:
    app.add_url_rule("/admin/audit", view_func=admin_required(admin_audit), methods=["GET"])
    app.add_url_rule("/admin.css", view_func=admin_css, methods=["GET"])
