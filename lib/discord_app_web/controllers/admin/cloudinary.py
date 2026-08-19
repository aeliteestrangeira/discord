from flask import jsonify, request
from lib.discord_app.cloudinary_service import CloudinaryError, SUPPORTED_IMAGE_SUFFIXES
from lib.discord_app.security import masked
from lib.discord_app_web.runtime import CLOUDINARY_IMPORT_DIR, STATIC_IMAGES_DIR, cloudinary
from lib.discord_app_web.security import admin_identity, admin_required, audit, require_admin_csrf

def admin_cloudinary_status():
    static_ok = False
    detail = "não configurado"
    try:
        snapshot = cloudinary.snapshot()
        static_ok = snapshot.configured
        detail = "configuração local válida" if static_ok else "configuração incompleta"
    except ValueError as exc:
        detail = str(exc)
    import_count = (
        sum(1 for path in CLOUDINARY_IMPORT_DIR.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES)
        if CLOUDINARY_IMPORT_DIR.is_dir() else 0
    )
    return jsonify({
        "ok": static_ok,
        "configured": cloudinary.configured,
        "cloud_name": cloudinary.cloud_name,
        "api_key": masked(cloudinary.api_key),
        "api_secret": masked(cloudinary.api_secret),
        "folder": cloudinary.folder,
        "detail": detail,
        "import_staging": "instance/cloudinary-import",
        "import_ready_files": import_count,
    })

def admin_cloudinary_config():
    require_admin_csrf()
    admin_id, username = admin_identity()
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload if isinstance(payload, dict) or hasattr(payload, "get") else {}
    try:
        changed = cloudinary.save_partial(
            admin_id=admin_id,
            cloud_name=str(payload.get("cloud_name") or "").strip(),
            api_key=str(payload.get("api_key") or "").strip(),
            api_secret=str(payload.get("api_secret") or "").strip(),
            folder=str(payload.get("folder") or "").strip(),
        )
        audit("admin", username, "cloudinary.config.update", "success", target=cloudinary.cloud_name, details={"changed": changed})
        return jsonify({"ok": True, "changed": changed, "configured": cloudinary.configured})
    except ValueError as exc:
        audit("admin", username, "cloudinary.config.update", "denied", target="cloudinary", details={"reason": "validation"})
        return jsonify({"ok": False, "error": {"code": "invalid_config", "message": str(exc)}}), 400

def admin_cloudinary_test():
    require_admin_csrf()
    _, username = admin_identity()
    ok, detail = cloudinary.test_connection()
    audit("admin", username, "cloudinary.connection_test", "success" if ok else "failure", target=cloudinary.cloud_name, details={"detail": detail})
    return jsonify({"ok": ok, "configured": cloudinary.configured, "detail": detail}), (200 if ok else 503)

def admin_cloudinary_migrate_images():
    require_admin_csrf()
    _, username = admin_identity()
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload if isinstance(payload, dict) or hasattr(payload, "get") else {}
    if str(payload.get("confirm") or "") != "MIGRAR":
        audit("admin", username, "cloudinary.images.migrate", "denied", target="images", details={"reason": "confirmation"})
        return jsonify({"ok": False, "error": {"code": "confirmation_required", "message": "Confirmação MIGRAR necessária."}}), 400
    try:
        source_dir = CLOUDINARY_IMPORT_DIR if CLOUDINARY_IMPORT_DIR.is_dir() else STATIC_IMAGES_DIR
        report = cloudinary.migrate_directory(source_dir, overwrite=bool(payload.get("overwrite", False)))
        outcome = "success" if not report.get("failed") else "failure"
        audit("admin", username, "cloudinary.images.migrate", outcome, target=cloudinary.cloud_name, details={"total": report.get("total"), "succeeded": report.get("succeeded"), "failed_count": len(report.get("failed") or [])})
        return jsonify({"ok": not bool(report.get("failed")), "report": report}), (200 if not report.get("failed") else 502)
    except CloudinaryError as exc:
        audit("admin", username, "cloudinary.images.migrate", "failure", target=cloudinary.cloud_name, details={"code": exc.code})
        return jsonify({"ok": False, "error": {"code": exc.code, "message": exc.public_message}}), 503


def register_routes(app) -> None:
    app.add_url_rule("/admin/cloudinary/status", view_func=admin_required(admin_cloudinary_status), methods=["GET"])
    app.add_url_rule("/admin/cloudinary/config", view_func=admin_required(admin_cloudinary_config), methods=["POST"])
    app.add_url_rule("/admin/cloudinary/test", view_func=admin_required(admin_cloudinary_test), methods=["POST"])
    app.add_url_rule("/admin/cloudinary/migrate-images", view_func=admin_required(admin_cloudinary_migrate_images), methods=["POST"])
