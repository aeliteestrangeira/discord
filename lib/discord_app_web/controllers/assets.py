from pathlib import Path
from flask import abort, redirect, send_from_directory
from lib.discord_app.cloudinary_service import CloudinaryError, SUPPORTED_IMAGE_SUFFIXES
from lib.discord_app_web.runtime import (
    ASSET_CSS_DIR, ASSET_JS_DIR, IMAGE_ASSET_ALIASES, PUBLIC_ROOT_FILES,
    STATIC_ASSETS_DIR, STATIC_FONTS_DIR, STATIC_IMAGES_DIR, UI_JS_DIR, UI_MODULE_FILES,
    cloudinary,
)

PINNED_CLOUDINARY_IMAGE_URLS = {
    "0082-d8680b1c1576ecc8.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132568/0082-d8680b1c1576ecc8_rrwlpk.svg",
    "0083-131c318dd45b7aa4.svg": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132620/0083-131c318dd45b7aa4_i9zgvc.svg",
    "login-qr-icon.png": "https://res.cloudinary.com/do7vwsnpg/image/upload/v1787132650/login-qr-icon_flnowo.png",
}


def public_root_asset(filename: str):
    if filename not in PUBLIC_ROOT_FILES:
        abort(404)
    if filename.endswith(".css"):
        return send_from_directory(ASSET_CSS_DIR, filename)
    return send_from_directory(ASSET_JS_DIR, filename)

def public_ui_module(filename: str):
    # ui.js é apenas um bootstrap loader; comportamento é dividido em um
    # conjunto fechado/allowlisted de módulos servido por esta rota.
    if filename not in UI_MODULE_FILES:
        abort(404)
    return send_from_directory(UI_JS_DIR, filename)

def font_asset(filename: str):
    if not filename.lower().endswith(".woff2"):
        abort(404)
    return send_from_directory(STATIC_FONTS_DIR, filename)

def image_asset(filename: str):
    # Keep every captured HTML/CSS URL byte-for-byte intact. While a local
    # migration source directory exists it remains the compatibility fallback;
    # once that heavy directory is removed from deployment, the exact same
    # /images/<name> URL resolves to an explicitly pinned Cloudinary delivery
    # URL first, then the configured dynamic Cloudinary fallback.
    clean = Path(filename).name
    if clean != filename or Path(clean).suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        abort(404)
    canonical = IMAGE_ASSET_ALIASES.get(clean, clean)
    local = STATIC_IMAGES_DIR / canonical
    if local.is_file():
        return send_from_directory(STATIC_IMAGES_DIR, canonical)
    external_url = PINNED_CLOUDINARY_IMAGE_URLS.get(canonical)
    if external_url:
        return redirect(external_url, code=302)
    if cloudinary.configured:
        try:
            return redirect(cloudinary.delivery_url(canonical), code=302)
        except CloudinaryError:
            pass
    abort(404)

def modal_asset(filename: str):
    # Default deny: this route exposes only assets explicitly allowlisted here.
    if filename not in {"a1c385fb82c39bab.svg", "88cde2b0ab4c8015cee8fdb8732b85b01df4fc78a75b3aa5e621539ea94b1803.svg"}:
        abort(404)
    return send_from_directory(STATIC_ASSETS_DIR, filename)


def register_routes(app) -> None:
    app.add_url_rule("/<filename>", view_func=public_root_asset, methods=["GET"])
    app.add_url_rule("/ui/<path:filename>", view_func=public_ui_module, methods=["GET"])
    app.add_url_rule("/fonts/<path:filename>", view_func=font_asset, methods=["GET"])
    app.add_url_rule("/images/<path:filename>", view_func=image_asset, methods=["GET"])
    app.add_url_rule("/assets/<path:filename>", view_func=modal_asset, methods=["GET"])
