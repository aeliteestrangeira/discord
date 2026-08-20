from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_LIB = ROOT / "lib" / "discord_app"
WEB_LIB = ROOT / "lib" / "discord_app_web"
WEB_TEMPLATES = WEB_LIB / "templates"
ASSET_JS = ROOT / "assets" / "js"
ASSET_UI_JS = ASSET_JS / "ui"
ASSET_CSS = ROOT / "assets" / "css"
STATIC_PAGES = ROOT / "priv" / "static" / "pages"
STATIC_ASSETS = ROOT / "priv" / "static" / "assets"
PRIV_SCRIPTS = ROOT / "priv" / "scripts"

WEB_SOURCE_ORDER = [
    WEB_LIB / "runtime.py", WEB_LIB / "registration.py", WEB_LIB / "security.py",
    WEB_LIB / "presenters.py", WEB_LIB / "controllers" / "pages.py",
    WEB_LIB / "controllers" / "guilds.py", WEB_LIB / "controllers" / "voice.py",
    WEB_LIB / "controllers" / "assets.py",
    WEB_LIB / "controllers" / "auth" / "security.py", WEB_LIB / "controllers" / "auth" / "passkey.py",
    WEB_LIB / "controllers" / "auth" / "login.py", WEB_LIB / "controllers" / "auth" / "registration.py",
    WEB_LIB / "controllers" / "auth" / "session.py", WEB_LIB / "controllers" / "friends.py", WEB_LIB / "controllers" / "admin" / "session.py",
    WEB_LIB / "controllers" / "admin" / "config.py", WEB_LIB / "controllers" / "admin" / "cloudinary.py",
    WEB_LIB / "controllers" / "admin" / "users.py", WEB_LIB / "controllers" / "admin" / "database.py",
    WEB_LIB / "controllers" / "admin" / "audit.py", WEB_LIB / "errors.py", WEB_LIB / "startup.py",
    WEB_LIB / "router.py", WEB_LIB / "app.py",
]

def web_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in WEB_SOURCE_ORDER)

EXPECTED = {
    "priv/static/pages/login.html": "f47ac7f6883755a6e0e7af28483e0e81a28945141cbb8d67b42ebb83ffce6d0c",
    "priv/static/pages/register.html": "f5606b079d6d6668845ebbbefb34a29b996a8df1b811ac27eb0eee7713a2675b",
    "priv/static/pages/channels.html": "f5ce7691c5f7a71981b4bf0ce33b11c4e553ad34896c600a87cba23816cdc588",
    "priv/static/pages/guild.html": "d05620a0e81f02db1e29bb932627c3bad5811e2d60e76c2e25c06da5c3d0e18c",
    "assets/css/discord.css": "c0e26f87a8d27037ce89f547383d9d4c27a9e7c03abc66d88f80ecbf7df543cb",
    "assets/css/channels.css": "d9564fe1aa5f219be8f89cd41a6750fd014b989afe8dddc7c9f54279dde387a2",
    "assets/css/guild.css": "a8ab1495491d96adf34cdd9d2d11d234679e72bf61d345632809e779832dbec9",
    "assets/css/captcha.css": "3a760d0ef6281340f74ff3f0e5f839006011235bc837f6115e87283a4a03ea82",
    "assets/css/admin.css": "5bc220360d385eb347e68517832d17965e062d8f698bb60efb5312652f38c935",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"FALHA: {message}")


def main() -> None:
    for rel, expected in EXPECTED.items():
        actual = sha256(ROOT / rel)
        if actual != expected:
            fail(f"baseline visual alterada em {rel}: {actual}")
        print(f"OK baseline: {rel}")

    login = (STATIC_PAGES / "login.html").read_text(encoding="utf-8")
    if "input__0ed4f input_d64f22 focused__0ed4f" in login:
        fail("login inicia com classe de foco transitória")
    if "input__0ed4f input_d64f22" not in login:
        fail("container neutro do primeiro input de login não encontrado")
    print("OK login inicia sem estado focused")

    register = (STATIC_PAGES / "register.html").read_text(encoding="utf-8")
    if 'type="checkbox"' not in register or 'checked=""' not in register:
        fail("checkbox original do cadastro não encontrado")
    print("OK checkbox original presente")

    frontend_paths = [
        STATIC_PAGES / "login.html",
        STATIC_PAGES / "register.html",
        ASSET_JS / "ui.js",
        ASSET_JS / "auth-provider.js",
        ASSET_CSS / "captcha.css",
        *(ASSET_UI_JS).glob("*.js"),
    ]
    frontend = "\n".join(path.read_text(encoding="utf-8") for path in frontend_paths)
    if re.search(r"sb_(?:secret|service_role)_[A-Za-z0-9_-]+", frontend):
        fail("chave privilegiada encontrada no frontend")
    if re.search(r"ES_[A-Za-z0-9_-]{20,}", frontend):
        fail("secret hCaptcha encontrado no frontend")
    if "postgresql://postgres:" in frontend:
        fail("string PostgreSQL encontrada no frontend")
    print("OK frontend sem credencial privilegiada")

    ui = (ASSET_JS / "ui.js").read_text(encoding="utf-8")
    ui_modules = "\n".join(path.read_text(encoding="utf-8") for path in (ASSET_UI_JS).glob("*.js"))
    ui_bundle = ui + "\n" + ui_modules
    auth_provider = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
    if "spinnerWrapper_a22cb0 fadeIn_a22cb0" not in ui_bundle or "pulsingEllipsis__46696" not in ui_bundle:
        fail("animacao de loading do botao de login ausente")
    if "requestCaptchaToken" not in ui_bundle or "https://js.hcaptcha.com/1/api.js" not in ui_bundle:
        fail("fluxo visual hCaptcha ausente")
    captcha_asset = STATIC_ASSETS / "a1c385fb82c39bab.svg"
    if not captcha_asset.is_file():
        fail("asset grafico do modal hCaptcha ausente")
    if 'new URL("../assets/a1c385fb82c39bab.svg", import.meta.url).href' not in ui_bundle:
        fail("modal hCaptcha nao referencia o asset grafico esperado")
    for required_class in ["headerGraphic__8a031", "headerGraphicContainer__8a031", "container__8ef77 aspect-ratio-16/9__8ef77", "image__8ef77"]:
        if required_class not in ui_bundle:
            fail(f"estrutura grafica do modal incompleta: {required_class}")
    if "hcaptchaToken" not in auth_provider:
        fail("token hCaptcha nao e encaminhado ao backend")
    print("OK loading e overlay hCaptcha no frontend")

    if 'loginCredentialErrorUi' not in ui_bundle or 'error__0ed4f' not in ui_bundle or 'statusMessageContainer__5a838' not in ui_bundle:
        fail("estado visual de credenciais invalidas ausente")
    if 'Login ou senha inválidos.' not in ui_bundle:
        fail("mensagem de credenciais invalidas ausente")
    print("OK estado visual de credenciais invalidas nos dois campos")

    if 'import(new URL("ui/bootstrap.js", appRoot).href)' not in ui:
        fail("ui.js nao e o bootstrap modular esperado")
    for module_name in [
        "bootstrap.js", "state.js", "runtime.js", "overlay-manager.js",
        "sliding-highlight.js", "menu-catalog.js", "captcha.js",
        "register-validation.js", "date-menu.js", "register-form.js", "login.js",
    ]:
        if not (ASSET_UI_JS / module_name).is_file():
            fail(f"modulo de UI ausente: {module_name}")
    if "SlidingHighlightController.ensureSingle" not in (ASSET_UI_JS / "date-menu.js").read_text(encoding="utf-8"):
        fail("sliding highlight compartilhado nao esta consolidado")
    if "OverlayManager.claim" not in (ASSET_UI_JS / "date-menu.js").read_text(encoding="utf-8"):
        fail("ownership de menu nao esta consolidado")
    print("OK arquitetura modular/overlay/highlight")

    privileged_bootstrap = ROOT / "config" / "SUPABASE_PRIVILEGED.env"
    if privileged_bootstrap.exists():
        if "SUPABASE_SERVICE_ROLE_KEY=" not in privileged_bootstrap.read_text(encoding="utf-8"):
            fail("service_role bootstrap ausente")
        print("OK arquivo bootstrap privilegiado presente")
    else:
        print("AVISO bootstrap privilegiado não está neste pacote; preservar .env/instance da instalação existente")
    source_without_bootstrap = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [*WEB_LIB.rglob("*.py"), *(APP_LIB).glob("*.py"), *(PRIV_SCRIPTS).glob("*.py"), *(WEB_TEMPLATES).rglob("*.html")]
    )
    jwt_prefix = "eyJhbGci" + "OiJIUzI1Ni"
    secret_prefix = "Yxks" + "vURf"
    if jwt_prefix in source_without_bootstrap or secret_prefix in source_without_bootstrap:
        fail("credencial privilegiada hardcoded no código")
    print("OK credenciais privilegiadas apenas no bootstrap mutável")

    forbidden = "SEC" + "522"
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".venv", "__pycache__", "instance", ".runtime", "architecture"} for part in path.parts):
            continue
        if path.suffix.lower() in {".woff2", ".png", ".webp", ".jpg", ".jpeg"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden in text:
            fail(f"referência proibida encontrada em {path.relative_to(ROOT)}")
    print("OK sem referência proibida no projeto")

    for path in [*WEB_LIB.rglob("*.py"), ROOT / "verify_architecture.py", *(APP_LIB).glob("*.py"), *(PRIV_SCRIPTS).glob("*.py"), *(ROOT / "test").glob("*.py")]:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print("OK sintaxe Python")

    app_text = web_source()
    if 'app.add_url_rule("/assets/<path:filename>"' not in app_text or '"a1c385fb82c39bab.svg"' not in app_text:
        fail("rota allowlist do asset grafico hCaptcha ausente")
    if 'app.add_url_rule("/ui/<path:filename>"' not in app_text or "UI_MODULE_FILES" not in app_text:
        fail("rota allowlist dos modulos de UI ausente")
    if (WEB_TEMPLATES / "admin" / "login.html").exists():
        fail("página exclusiva de login administrativo ainda existe")
    if 'app.add_url_rule("/admin/login"' in app_text or 'admin/login.html' in app_text:
        fail("rota exclusiva de login administrativo ainda existe")
    if '"redirect": "/admin"' not in app_text or 'role="admin"' not in app_text:
        fail("login unificado não contém fluxo administrativo server-side")
    print("OK login administrativo unificado na página pública")

    if 'app.add_url_rule("/"' not in app_text or 'send_from_directory(STATIC_PAGES_DIR, "login.html")' not in app_text:
        fail("login canonico na raiz ausente")
    if 'app.add_url_rule("/login.html"' not in app_text or 'app.add_url_rule("/login"' not in app_text or 'redirect(url_for("home")' not in app_text:
        fail("aliases legados de login nao redirecionam para a raiz")
    if 'Start-Process "https://${appHost}:$Port/"' not in (PRIV_SCRIPTS / "restart_server.ps1").read_text(encoding="utf-8"):
        fail("supervisor ainda abre caminho explicito de login")
    print("OK URL canonica de login somente na raiz")

    hcaptcha_service = (APP_LIB / "hcaptcha_service.py").read_text(encoding="utf-8")
    if "captcha.verify(captcha_token" not in app_text or app_text.index("captcha.verify(captcha_token") > app_text.index("store.authenticate_admin(identifier, password)"):
        fail("hCaptcha nao e validado antes da autoridade de identidade")
    if "https://api.hcaptcha.com/siteverify" not in hcaptcha_service:
        fail("endpoint siteverify oficial ausente")
    for required in ['"secret"', '"response"', '"sitekey"', '"remoteip"']:
        if required not in hcaptcha_service:
            fail(f"parametro hCaptcha ausente: {required}")
    if not (PRIV_SCRIPTS / "ensure_local_hostname.ps1").exists():
        fail("preparo de hostname local hCaptcha ausente")
    if "priv\\scripts\\ensure_local_hostname.ps1" not in (ROOT / "SERVER.bat").read_text(encoding="utf-8"):
        fail("SERVER.bat nao prepara hostname local hCaptcha")
    print("OK hCaptcha server-side default deny antes da autenticacao")

    # Authentication hardening: public responses must not reveal account
    # existence.  The application's Host header is strict/default-deny, while
    # the provider's siteverify success remains authoritative for hCaptcha.
    login_start = app_text.index("def api_login():")
    login_end = app_text.index('def api_login_link():', login_start)
    login_block = app_text[login_start:login_end]
    recovery_start = app_text.index("def api_login_link():")
    recovery_end = app_text.index("def _username_candidate_base", recovery_start)
    recovery_block = app_text[recovery_start:recovery_end]
    login_js = (ASSET_UI_JS / "login.js").read_text(encoding="utf-8")
    validators = (APP_LIB / "validators.py").read_text(encoding="utf-8")
    if "provider.auth_email_exists(identifier)" in login_block or '"code": "email_not_found"' in login_block:
        fail("login ainda expoe existencia de conta")
    if "provider.auth_email_exists(identifier)" in recovery_block or "Se a conta existir e estiver apta" not in recovery_block:
        fail("recuperacao ainda expoe existencia de conta")
    if "email_not_found" in login_js:
        fail("frontend ainda diferencia conta inexistente")
    if "def reject_untrusted_host" not in app_text or "ALLOWED_HOSTS = frozenset({APP_HOSTNAME})" not in app_text:
        fail("hostname canonico/Host default-deny ausente")
    if 'success = bool(data.get("success"))' not in hcaptcha_service or 'hostname = str(data.get("hostname") or "")' not in hcaptcha_service:
        fail("resultado siteverify/hostname hCaptcha nao e preservado")
    if "hostname-mismatch" in hcaptcha_service or "hostname_allowed(" in hcaptcha_service:
        fail("hCaptcha ainda cria rejeicao local por hostname em vez de respeitar siteverify")
    if "PASSWORD_MIN_LENGTH = 16" not in validators or "validate_password_strength" not in validators:
        fail("politica forte de senha ausente")
    harden = (PRIV_SCRIPTS / "harden_instance.ps1").read_text(encoding="utf-8")
    if "SUPABASE_PRIVILEGED.env" not in harden or '"*${userSid}:F"' not in harden:
        fail("ACL do bootstrap privado nao e endurecida")
    # Page/component loading: login must not pull registration-only controllers,
    # and heavy authenticated features must stay behind dynamic imports.
    bootstrap_js = (ASSET_UI_JS / "bootstrap.js").read_text(encoding="utf-8")
    channels_js = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
    if 'from "./date-menu.js"' in bootstrap_js or 'from "./register-validation.js"' in bootstrap_js:
        fail("login ainda carrega modulos exclusivos de registro")
    for marker in ('import("./login.js")', 'import("./date-menu.js")', 'import("./channels.js")'):
        if marker not in bootstrap_js:
            fail(f"bootstrap sob demanda ausente: {marker}")
    for heavy in ('server-entry', 'voice'):
        if f'from "./{heavy}.js"' in channels_js or f'loadModule("{heavy}")' not in channels_js:
            fail(f"modulo pesado nao esta lazy-loaded: {heavy}")
    print("OK carregamento JS por rota/componente sob demanda")

    print("OK hardening de autenticacao, Host, hCaptcha, senhas e ACL")

    if "--instance-marker" not in app_text:
        fail("marcador de propriedade do processo ausente")
    print("OK marcador de propriedade do servidor")

    layout_failures = check_elixir_layout_and_voice_audio()
    if layout_failures:
        fail("; ".join(layout_failures))
    print("OK layout Elixir/Phoenix e audio de voz")

    print("PRECHECK concluído com sucesso")


def check_elixir_layout_and_voice_audio():
    failures = []
    for name in ("assets", "config", "lib", "priv", "test"):
        if not (ROOT / name).is_dir(): failures.append(f"missing layout dir: {name}")
    for obsolete in ("core", "frontend", "fonts", "templates", "tests", "architecture", "supabase", "scripts"):
        if (ROOT / obsolete).exists(): failures.append(f"obsolete root dir remains: {obsolete}")
    sounds = ASSET_UI_JS / "voice-sounds.js"
    voice = ASSET_UI_JS / "voice.js"
    if not sounds.is_file(): failures.append("voice-sounds.js missing")
    else:
        source = sounds.read_text(encoding="utf-8")
        for marker in ("529ff198eac567af_nhesmn.mp3", "b150f03c89944403_qvpaen.mp3", "2d3b4ba32c34c862_ooopar.mp3", "e74c4a06134a20e4_kzqukf.mp3"):
            if marker not in source: failures.append(f"voice sound missing: {marker}")
    if voice.is_file():
        source = voice.read_text(encoding="utf-8")
        for marker in ("setMicrophoneMuted", "setHeadphonesMuted", "app:voice-control"):
            if marker not in source: failures.append(f"voice state hook missing: {marker}")
    return failures


if __name__ == "__main__":
    main()
