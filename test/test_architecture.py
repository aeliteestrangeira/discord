from __future__ import annotations

import hashlib
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from lib.discord_app.access import Actor, Policy


ROOT = Path(__file__).resolve().parents[1]
APP_LIB = ROOT / "lib" / "discord_app"
WEB_LIB = ROOT / "lib" / "discord_app_web"
WEB_TEMPLATES = WEB_LIB / "templates"
ASSET_JS = ROOT / "assets" / "js"
ASSET_UI_JS = ASSET_JS / "ui"
ASSET_CSS = ROOT / "assets" / "css"
STATIC_PAGES = ROOT / "priv" / "static" / "pages"
STATIC_FONTS = ROOT / "priv" / "static" / "fonts"
STATIC_ASSETS = ROOT / "priv" / "static" / "assets"
PRIV_ARCH = ROOT / "priv" / "architecture"
PRIV_SUPABASE_MIGRATIONS = ROOT / "priv" / "supabase" / "migrations"
PRIV_SCRIPTS = ROOT / "priv" / "scripts"
GENERATED_TREE_PARTS = {
    ".git", ".venv", ".runtime", "instance", "node_modules", "out", "build",
    ".pytest_cache", "__pycache__",
}

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



class CaptureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tag_count = 0
        self.class_token_count = 0
        self.unique_classes: set[str] = set()
        self.modal_close_buttons = 0
        self.verification_notices = 0
        self.account_username_nodes = 0
        self.avatar_source = ""
        self.script_tags = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_count += 1
        data = {key: value or "" for key, value in attrs}
        classes = [value for value in data.get("class", "").split() if value]
        self.class_token_count += len(classes)
        self.unique_classes.update(classes)
        if tag == "script":
            self.script_tags += 1
        if tag == "button" and {"closeButton_f17563", "close__49fc1"}.issubset(classes):
            self.modal_close_buttons += 1
        if "notice__6e2b9" in classes:
            self.verification_notices += 1
        if "title_b6c092" in classes:
            self.account_username_nodes += 1
        if tag == "img" and "avatar__44b0c" in classes:
            self.avatar_source = data.get("src", "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


class ArchitectureTests(unittest.TestCase):
    def test_actor_never_upgrades_missing_session(self):
        self.assertEqual(Actor.from_browser_session(None), Actor.anonymous())
        self.assertEqual(Actor.from_browser_session({"role": "admin", "user_id": ""}), Actor.anonymous())
        self.assertEqual(Actor.from_browser_session({"role": "root", "user_id": "user-1"}), Actor.anonymous())

    def test_admin_actor_requires_local_admin_identity_shape(self):
        actor = Actor.from_browser_session({"role": "admin", "user_id": "local-admin:7"})
        self.assertTrue(actor.authenticated)
        self.assertEqual(actor.role, "admin")
        self.assertEqual(actor.authority, "local-control")
        self.assertTrue(Policy.allowed(actor, "admin.access"))
        self.assertFalse(Policy.allowed(actor, "shell.read"))

    def test_normal_user_cannot_access_admin(self):
        actor = Actor.from_browser_session({"role": "user", "user_id": "user-1"})
        self.assertTrue(Policy.allowed(actor, "shell.read"))
        self.assertFalse(Policy.allowed(actor, "admin.access"))
        self.assertFalse(Policy.allowed(actor, "email.resend"))
        self.assertTrue(Policy.allowed(actor, "friend.request.create"))
        self.assertTrue(Policy.allowed(actor, "friend.request.read"))
        self.assertTrue(Policy.allowed(actor, "friend.request.cancel"))
        self.assertTrue(Policy.allowed(actor, "friend.request.accept"))
        self.assertTrue(Policy.allowed(actor, "friend.request.ignore"))
        self.assertTrue(Policy.allowed(actor, "voice.connect"))
        self.assertFalse(Policy.allowed(actor, "email.change"))

    def test_pending_actor_is_restricted_to_shell_and_verification(self):
        actor = Actor.from_browser_session({"role": "pending", "user_id": "user-1"})
        self.assertTrue(actor.authenticated)
        self.assertEqual(actor.authority, "supabase-auth-pending")
        self.assertTrue(Policy.allowed(actor, "shell.read"))
        self.assertTrue(Policy.allowed(actor, "email.resend"))
        self.assertTrue(Policy.allowed(actor, "email.verify.refresh"))
        self.assertTrue(Policy.allowed(actor, "email.change"))
        self.assertTrue(Policy.allowed(actor, "friend.request.create"))
        self.assertTrue(Policy.allowed(actor, "friend.request.read"))
        self.assertTrue(Policy.allowed(actor, "friend.request.cancel"))
        self.assertTrue(Policy.allowed(actor, "friend.request.accept"))
        self.assertTrue(Policy.allowed(actor, "friend.request.ignore"))
        self.assertTrue(Policy.allowed(actor, "voice.connect"))
        self.assertFalse(Policy.allowed(actor, "admin.access"))
        self.assertFalse(Policy.allowed(actor, "admin.write"))

    def test_frontend_is_split_and_ui_entrypoint_is_loader_only(self):
        ui = (ASSET_JS / "ui.js").read_text(encoding="utf-8")
        self.assertIn('import(new URL("ui/bootstrap.js", appRoot).href)', ui)
        self.assertLess(len(ui.splitlines()), 40)
        for filename in [
            "state.js", "runtime.js", "dom.js", "overlay-manager.js", "sliding-highlight.js",
            "menu-catalog.js", "captcha.js", "register-validation.js", "date-menu.js",
            "register-form.js", "login.js", "channels.js", "account-verification.js",
            "friends.js", "friend-pending.js", "direct-messages.js", "session-watchdog.js", "server-entry.js", "voice.js", "voice-capture.js", "voice-sounds.js", "bootstrap.js",
        ]:
            self.assertTrue((ASSET_UI_JS / filename).is_file(), filename)

    def test_date_menus_use_one_catalog_and_shared_highlight_controller(self):
        date_source = (ASSET_UI_JS / "date-menu.js").read_text(encoding="utf-8")
        self.assertIn("dateOfBirthMenuCatalog", date_source)
        self.assertIn("SlidingHighlightController.ensureSingle", date_source)
        self.assertIn("OverlayManager.claim", date_source)
        self.assertNotIn("const monthLabels =", date_source)

    def test_protected_html_css_baseline_hashes_are_unchanged(self):
        expected = {
            "login.html": "f47ac7f6883755a6e0e7af28483e0e81a28945141cbb8d67b42ebb83ffce6d0c",
            "register.html": "f5606b079d6d6668845ebbbefb34a29b996a8df1b811ac27eb0eee7713a2675b",
            "discord.css": "c0e26f87a8d27037ce89f547383d9d4c27a9e7c03abc66d88f80ecbf7df543cb",
            "channels.css": "d9564fe1aa5f219be8f89cd41a6750fd014b989afe8dddc7c9f54279dde387a2",
            "guild.html": "d05620a0e81f02db1e29bb932627c3bad5811e2d60e76c2e25c06da5c3d0e18c",
            "guild.css": "a8ab1495491d96adf34cdd9d2d11d234679e72bf61d345632809e779832dbec9",
            "channels.html": "f5ce7691c5f7a71981b4bf0ce33b11c4e553ad34896c600a87cba23816cdc588",
            "captcha.css": "3a760d0ef6281340f74ff3f0e5f839006011235bc837f6115e87283a4a03ea82",
            "admin.css": "5bc220360d385eb347e68517832d17965e062d8f698bb60efb5312652f38c935",
            "templates/admin/audit.html": "586f0272ef3f01ebaaecf0aeb381aebea0e14e7b754e4f392d97a97f67647671",
            "templates/admin/base.html": "c4685f72b1454d627cf4ce5f39a7f69ad4ae60ffa0856dfebde689bd6f45f517",
            "templates/admin/config.html": "a528f2b5b94dacb278b517c8a4e3b0149f82961ce7a6cda324691f9db9cce27a",
            "templates/admin/dashboard.html": "6ff9ece9a20daefc152621b6aa913d8b5795f7d4dad55d5e05df1b1b434b8493",
            "templates/admin/sql.html": "d9abdb15521a7c5d64006c6e048dd6c55582a72f59910534ecc0f585fe5fc676",
            "templates/admin/tables.html": "7d217fba5cad8a5ca8dfc4dbf6619d533b65febbb7bd17200c97ac5d51cad70f",
            "templates/admin/users.html": "48a8e423f8faa71be6d6fdba74096d7e691f41bf58bf0e9f9c74ad844be605b5",
        }
        for filename, digest in expected.items():
            if filename.endswith(".html") and not filename.startswith("templates/"):
                path = STATIC_PAGES / filename
            elif filename.endswith(".css"):
                path = ASSET_CSS / filename
            elif filename.startswith("templates/"):
                path = WEB_LIB / filename
            else:
                path = ROOT / filename
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, digest, filename)

    def test_channels_capture_structure_matches_recorded_baseline(self):
        baseline = json.loads((PRIV_ARCH / "channels-baseline.json").read_text(encoding="utf-8"))
        parser = CaptureParser()
        parser.feed((STATIC_PAGES / "channels.html").read_text(encoding="utf-8"))
        self.assertEqual(parser.tag_count, baseline["tag_count"])
        self.assertEqual(parser.class_token_count, baseline["class_token_count"])
        self.assertEqual(len(parser.unique_classes), baseline["unique_class_count"])
        self.assertEqual(parser.modal_close_buttons, baseline["modal_close_buttons"])
        self.assertEqual(parser.verification_notices, baseline["verification_notices"])
        self.assertEqual(parser.account_username_nodes, baseline["account_username_nodes"])
        self.assertEqual(parser.avatar_source, baseline["avatar_source"])
        self.assertEqual(parser.script_tags, 0, "captured source must stay script-free")

    def test_channels_has_no_captured_drag_previewer_overlay(self):
        html = (STATIC_PAGES / "channels.html").read_text(encoding="utf-8")
        self.assertNotIn('class="drag-previewer"', html)
        self.assertNotIn('<svg style="contain: paint;"><foreignobject></foreignobject></svg>', html)

    def test_channels_css_reuses_shared_css_and_fonts_are_deduplicated(self):
        css = (ASSET_CSS / "channels.css").read_text(encoding="utf-8")
        self.assertTrue(css.startswith('@import url("discord.css");'))
        fonts = sorted(path for path in STATIC_FONTS.glob("*.woff2") if path.is_file())
        self.assertEqual(len(fonts), 55)
        digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in fonts]
        self.assertEqual(len(digests), len(set(digests)), "fontes duplicadas por conteúdo")

    def test_authenticated_shell_is_not_anonymous_static_content(self):
        app_source = web_source()
        self.assertIn('app.add_url_rule("/channels/@me"', app_source)
        self.assertIn('Policy.allowed(actor, "shell.read")', app_source)
        self.assertIn('html.replace("aeliteestrangeira", html_escape(username))', app_source)
        self.assertIn('html = html.replace(captured_notice, "", 1)', app_source)
        public_block = re.search(r"PUBLIC_ROOT_FILES\s*=\s*\{(.*?)\n\}", app_source, re.S)
        self.assertIsNotNone(public_block)
        self.assertNotIn("channels.html", public_block.group(1))
        for anonymous_page in ["login.html", "register.html"]:
            source = (STATIC_PAGES / anonymous_page).read_text(encoding="utf-8")
            self.assertNotIn("/channels/@me", source)

    def test_registration_and_user_login_transition_to_authenticated_shell(self):
        register = (ASSET_UI_JS / "register-form.js").read_text(encoding="utf-8")
        login = (ASSET_UI_JS / "login.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('navigate(result.data?.redirect || "/channels/@me")', register)
        self.assertIn('navigate(result.data?.redirect || "/channels/@me")', login)
        self.assertGreaterEqual(app_source.count('"redirect": "/channels/@me"'), 3)
        self.assertIn('role = "user" if email_confirmed else "pending"', app_source)

    def test_unconfirmed_password_login_becomes_restricted_pending_session(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        login_block = app_source[app_source.index('def api_login():'):app_source.index('def api_login_link():')]
        self.assertIn('exc.code == "email_not_confirmed"', login_block)
        self.assertIn('provider.pending_email_identity(identifier)', login_block)
        self.assertIn('role = "user" if email_confirmed else "pending"', login_block)
        self.assertIn('target="local-pending-session" if role == "pending" else "supabase-auth"', login_block)
        self.assertIn('"status": "confirmation-pending" if role == "pending" else "authenticated"', login_block)
        self.assertIn('"credential_proof": "supabase-email-not-confirmed"', login_block)
        self.assertIn('def pending_email_identity', provider_source)
        pending_block = provider_source[provider_source.index('def pending_email_identity'):provider_source.index('def auth_email_exists')]
        self.assertNotIn('u.encrypted_password', pending_block)
        self.assertIn('"access_token": None', pending_block)
        self.assertIn('"refresh_token": None', pending_block)
        self.assertIn('"verification_kind": "signup"', pending_block)

    def test_email_confirmation_state_is_not_inferred_from_provider_session(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        block = provider_source[provider_source.index('def _extract_auth_response'):provider_source.index('def _auth_api_json')]
        confirmation_block = block[block.index('email_confirmed = bool('):block.index('return {')]
        self.assertIn('email_confirmed_at', confirmation_block)
        self.assertIn('confirmed_at', confirmation_block)
        self.assertNotIn('or session', confirmation_block)

    def test_verification_endpoints_use_server_side_actor_and_session_email(self):
        app_source = web_source()
        self.assertIn('app.add_url_rule("/api/auth/verification/status"', app_source)
        self.assertIn('app.add_url_rule("/api/auth/resend-confirmation"', app_source)
        self.assertIn('Policy.allowed(actor, "email.verify.refresh")', app_source)
        self.assertIn('Policy.allowed(actor, "email.resend")', app_source)
        self.assertIn('email = str(row["email"] or "").strip().lower()', app_source)
        resend_source = (WEB_LIB / 'controllers' / 'auth' / 'session.py').read_text(encoding='utf-8')
        resend_block = resend_source[resend_source.index('def api_resend_confirmation'):resend_source.index('def api_change_email():')]
        self.assertNotIn('payload.get("email")', resend_block)

    def test_channels_runtime_only_wires_requested_actions(self):
        source = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        verification = (ASSET_UI_JS / "account-verification.js").read_text(encoding="utf-8")
        server_entry = (ASSET_UI_JS / "server-entry.js").read_text(encoding="utf-8")
        self.assertIn("button.closeButton_f17563.close__49fc1", server_entry)
        self.assertIn("wireServerEntry", source)
        self.assertIn("wireVerificationNotice", source)
        self.assertIn("wireFriendRequests", source)
        self.assertIn("wirePendingFriendRequests", source)
        self.assertIn("resendConfirmation", verification)
        self.assertIn("readSessionBootstrap", source)
        self.assertIn('document.getElementById("app-session-bootstrap")', source)
        self.assertNotIn("verificationStatus", source, "verification refresh must not block channels boot")
        self.assertNotIn(".animate(", source + verification, "do not invent a parallel modal animation system")
        self.assertIn(".title_b6c092, .hovered__0263c", source)
        self.assertNotIn("aeliteestrangeira", source)
        self.assertNotIn("translateCapturedDom", source + verification)
        self.assertNotIn("TEXT_PT_BR", source + verification)
        self.assertNotIn("ATTRIBUTE_PT_BR", source + verification)
        self.assertNotIn("createTreeWalker", source + verification)


    def test_server_entry_reuses_captured_tutorial_and_modal_classes_without_css_changes(self):
        source = (ASSET_UI_JS / "server-entry.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('"server-entry.js",', app_source)
        self.assertIn('[data-list-item-id="guildsnav___create-join-button"]', source)
        self.assertIn('tutorialContainer__650eb', source)
        self.assertIn('indicator_ffc7aa', source)
        self.assertIn('clickTrapContainer__59d0d', source)
        self.assertIn('popoutRoot__22234 contentNarrowNoMedia__22234', source)
        self.assertIn('Crie seu próprio servidor', source)
        self.assertIn('Entendi!', source)
        self.assertIn('Pular todas as dicas', source)
        self.assertIn('modal__024d4 root__49fc1 small__49fc1 rootWithShadow__49fc1', source)
        self.assertIn('Crie seu servidor', source)
        self.assertIn('/images/0209-b30f13ee315c2568.svg', source)
        self.assertIn('/images/0211-050c2ac76232eff6.svg', source)
        self.assertIn('OverlayManager.claim({ id: "first-server-tip", type: "menu", close })', source)
        self.assertIn('OverlayManager.claim({ id: CREATE_SERVER_OVERLAY, type: "modal", close })', source)
        self.assertIn('safeLocalStorageSet(seenKey, "1")', source)
        self.assertIn('safeLocalStorageSet(skipKey, "1")', source)
        self.assertIn('slide.animate([', source)
        self.assertIn('prefers-reduced-motion: reduce', source)

    def test_channels_localization_is_baked_into_html_not_runtime(self):
        html = (STATIC_PAGES / "channels.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="pt-BR"', html)
        self.assertIn('<title>(1) Discord | Amigos</title>', html)
        self.assertIn("Crie seu primeiro servidor do Discord", html)
        self.assertIn("Verifique seu e-mail para confirmar sua conta e manter seu nome de usuário atual.", html)
        self.assertIn('aria-label="Fechar"', html)
        self.assertNotIn("Create Your First Discord Server", html)
        self.assertNotIn("Please check your email to verify your account and keep your current username.", html)
        self.assertNotIn('aria-label="Close"', html)

    def test_yaml_documents_same_closed_flow_without_becoming_runtime_authority(self):
        yaml_source = (PRIV_ARCH / "app-flow.yaml").read_text(encoding="utf-8")
        self.assertIn("route: /channels/@me", yaml_source)
        self.assertIn("pending:", yaml_source)
        self.assertIn("default: deny", yaml_source)
        self.assertIn("other_actions: inert", yaml_source)
        self.assertIn("preferred_when_admin_configured: trusted Auth Admin create_user, email_confirm=false", yaml_source)
        self.assertIn("confirmation_delivery_failure: keep account pending and allow retry", yaml_source)
        self.assertIn("fallback_without_admin_authority: Supabase public sign-up", yaml_source)
        self.assertIn("runtime_translation_script: false", yaml_source)
        self.assertIn("source_owned: true", yaml_source)
        app_source = web_source()
        self.assertNotIn("app-flow.yaml", app_source)

    def test_registration_schema_is_verified_and_self_healed(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        self.assertIn("provider.ensure_application_schema()", app_source)
        self.assertIn("provider.application_schema_status()", app_source)
        self.assertIn("def registration_schema_status", provider_source)
        self.assertIn("to_regclass('public.profiles')", provider_source)
        self.assertIn("on_auth_user_created_profile", provider_source)
        self.assertIn("profiles_username_unique", provider_source)
        self.assertIn("profiles_username_format", provider_source)
        self.assertIn("profiles_username_no_repeating_dots", provider_source)
        self.assertIn("self.apply_core_migration()", provider_source)
        self.assertIn("def ensure_application_schema", provider_source)
        migrations = list(PRIV_SUPABASE_MIGRATIONS.glob("*.sql"))
        self.assertEqual([path.name for path in migrations], ["000_current_schema.sql"])
        app_source = web_source()
        self.assertIn("def prepare_registration_schema_at_startup", app_source)
        self.assertIn("prepare_registration_schema_at_startup()", app_source)


    def test_registration_admin_path_is_hcaptcha_gated(self):
        register_source = (ASSET_UI_JS / "register-form.js").read_text(encoding="utf-8")
        auth_source = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('import("./captcha.js")', register_source)
        self.assertIn("const hcaptchaToken = await requestCaptchaToken();", register_source)
        self.assertIn("State.marketingOptIn, hcaptchaToken", register_source)
        self.assertIn("async function signUp(email, password, profile, marketingOptIn, hcaptchaToken)", auth_source)
        register_block = app_source[app_source.index('def api_register():'):app_source.index('def api_session():')]
        self.assertIn('payload.get("hcaptchaToken")', register_block)
        self.assertIn('captcha.verify(captcha_token, request.remote_addr)', register_block)
        self.assertLess(register_block.index('captcha.verify(captcha_token, request.remote_addr)'), register_block.index('provider.create_registration_user(email, password, metadata)'))

    def test_registration_is_server_owned_when_admin_authority_is_available(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        register_source = (ASSET_UI_JS / "register-form.js").read_text(encoding="utf-8")
        self.assertIn("if provider.admin_configured:", app_source)
        self.assertIn("provider.create_registration_user(email, password, metadata)", app_source)
        self.assertIn("provider.sign_up(email, password, metadata)", app_source)
        self.assertIn("def create_registration_user", provider_source)
        self.assertIn('client.auth.admin.create_user', provider_source)
        self.assertIn('attributes["user_metadata"] = metadata', provider_source)
        self.assertIn('result["creation_mode"] = "server-admin-create"', provider_source)
        self.assertIn('result["verification_kind"] = "signup"', provider_source)
        self.assertIn("self.resend_signup_confirmation(email)", provider_source)
        self.assertNotIn("service_role", register_source)
        self.assertNotIn("SUPABASE_SECRET_KEY", register_source)

    def test_registration_email_delivery_is_best_effort_after_persist(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        app_source = web_source()
        block = provider_source[provider_source.index("def create_registration_user"):provider_source.index("def invite_user", provider_source.index("def create_registration_user"))]
        self.assertIn("created = self.create_user", block)
        self.assertIn("confirmation_email_sent = False", block)
        self.assertIn("self.resend_signup_confirmation(email)", block)
        self.assertIn('result["email_confirmed"] = False', block)
        self.assertIn('"auth.register.confirmation-email", "failure"', app_source)

    def test_resend_uses_session_verification_kind_not_browser_input(self):
        app_source = web_source()
        block = app_source[app_source.index('def api_resend_confirmation'):app_source.index('def api_logout():')]
        self.assertIn('verification_kind = str(row["verification_kind"]', block)
        self.assertIn('if verification_kind == "invite"', block)
        self.assertIn('provider.invite_user(email)', block)
        self.assertIn('provider.resend_signup_confirmation(email)', block)
        self.assertNotIn('payload.get("verification_kind")', block)

    def test_admin_tables_are_real_supabase_catalog_with_local_control_separated(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        table_template = (WEB_TEMPLATES / "admin" / "tables.html").read_text(encoding="utf-8")
        self.assertIn("provider.list_schemas()", app_source)
        self.assertIn("provider.list_tables(selected_schema)", app_source)
        self.assertIn("provider.describe_table(selected_schema, selected_table)", app_source)
        self.assertIn("def list_schemas", provider_source)
        self.assertIn("def describe_table", provider_source)
        self.assertIn("Supabase PostgreSQL", table_template)
        self.assertIn("Controle local — não é Supabase", table_template)
        self.assertIn("app_private.schema_migrations", table_template)

    def test_current_schema_is_recorded_by_sha256_in_private_supabase_schema(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        schema_sql = (PRIV_SUPABASE_MIGRATIONS / "000_current_schema.sql").read_text(encoding="utf-8")
        self.assertIn("app_private.schema_migrations", provider_source)
        self.assertIn('state = "outdated"', provider_source)
        self.assertIn("hashlib.sha256(migration_path.read_bytes()).hexdigest()", provider_source)
        self.assertIn("on conflict (migration) do update", provider_source.lower())
        self.assertIn("create schema if not exists app_private", schema_sql.lower())
        self.assertIn("create table if not exists app_private.schema_migrations", schema_sql.lower())
        self.assertIn("create table if not exists app_private.email_delivery_events", schema_sql.lower())
        self.assertNotIn("recipient text", schema_sql.lower())

    def test_sql_console_blocks_writes_to_supabase_managed_schemas(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        sql_template = (WEB_TEMPLATES / "admin" / "sql.html").read_text(encoding="utf-8")
        self.assertIn("sql_managed_schema_blocked", provider_source)
        self.assertIn("auth|storage|realtime|extensions|graphql|vault", provider_source)
        self.assertIn("schemas gerenciados pelo Supabase", sql_template)
        self.assertIn("public", sql_template)
        self.assertIn("app_private", sql_template)

    def test_gmail_is_prepared_but_not_activated(self):
        app_source = web_source()
        mail_source = (APP_LIB / "mail_config.py").read_text(encoding="utf-8")
        config_template = (WEB_TEMPLATES / "admin" / "config.html").read_text(encoding="utf-8")
        self.assertIn('return "supabase"', mail_source)
        self.assertIn("https://www.googleapis.com/auth/gmail.send", mail_source)
        self.assertIn("GOOGLE_GMAIL_CLIENT_SECRET", mail_source)
        self.assertIn("GOOGLE_GMAIL_REFRESH_TOKEN", mail_source)
        self.assertIn("Gmail API (preparação)", config_template)
        self.assertIn("console.cloud.google.com/apis/credentials", app_source)
        self.assertIn('target="_blank" rel="noopener noreferrer"', config_template)
        self.assertNotIn("gmail_password", mail_source)

    def test_email_delivery_telemetry_uses_hash_not_plain_recipient(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn("def record_email_delivery_event", provider_source)
        self.assertIn("recipient_hash = hashlib.sha256", provider_source)
        self.assertIn("app_private.email_delivery_events", provider_source)
        self.assertIn('provider="supabase"', app_source)



    def test_friend_request_flow_is_hcaptcha_gated_and_server_resolves_target(self):
        app_source = web_source()
        auth_source = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        friend_source = (ASSET_UI_JS / "friends.js").read_text(encoding="utf-8")
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        migration = (PRIV_SUPABASE_MIGRATIONS / "000_current_schema.sql").read_text(encoding="utf-8")
        self.assertIn('app.add_url_rule("/api/friends/requests"', app_source)
        friend_routes = (WEB_LIB / 'controllers' / 'friends.py').read_text(encoding='utf-8')
        block = friend_routes[friend_routes.index('def api_friend_request():'):friend_routes.index('def api_pending_friend_requests():')]
        self.assertIn('captcha.verify(captcha_token, request.remote_addr)', block)
        self.assertIn('provider.create_friend_request(actor.id, username)', block)
        self.assertLess(block.index('captcha.verify(captcha_token, request.remote_addr)'), block.index('provider.create_friend_request(actor.id, username)'))
        self.assertIn('requestCaptchaToken()', friend_source)
        self.assertIn('authProvider.sendFriendRequest(username, hcaptchaToken)', friend_source)
        self.assertIn('error__72ba7', friend_source)
        self.assertIn('success__72ba7', friend_source)
        self.assertIn('showVerificationRequired(authProvider)', friend_source)
        self.assertIn('async function sendFriendRequest(username, hcaptchaToken)', auth_source)
        self.assertIn('FROM public.profiles p', provider_source)
        self.assertIn('INSERT INTO public.friend_requests', provider_source)
        self.assertIn('create table if not exists public.friend_requests', migration.lower())
        self.assertIn('sender_id uuid not null references auth.users', migration.lower())
        self.assertIn('receiver_id uuid not null references auth.users', migration.lower())
        self.assertIn('enable row level security', migration.lower())

    def test_friend_request_button_activates_from_first_character_and_success_locks_until_edit(self):
        source = (ASSET_UI_JS / "friends.js").read_text(encoding="utf-8")
        self.assertIn('submit.disabled = value.length === 0 || (completedValue && value === completedValue);', source)
        self.assertIn('completedValue = input.value.trim();', source)
        self.assertIn('completedValue = "";', source)
        self.assertIn('Seu pedido de amizade para', source)
        self.assertIn('Confira se o nome de usuário está correto.', source)

    def test_verification_required_and_change_email_use_captured_markup_and_local_svg(self):
        source = (ASSET_UI_JS / "account-verification.js").read_text(encoding="utf-8")
        app_source = web_source()
        auth_source = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        asset = STATIC_ASSETS / "88cde2b0ab4c8015cee8fdb8732b85b01df4fc78a75b3aa5e621539ea94b1803.svg"
        self.assertTrue(asset.is_file())
        self.assertIn('root__5c9fc enterDone__5c9fc', source)
        self.assertIn('verification_dede4b', source)
        self.assertIn('Verificação necessária', source)
        self.assertIn('Verificar por e-mail', source)
        self.assertIn('Reenviar e-mail', source)
        self.assertIn('Alterar e-mail', source)
        self.assertIn('A senha não corresponde.', source)
        self.assertIn('O e-mail já está registrado.', source)
        self.assertIn('submit.disabled = !(emailInput.value.length > 0 && passwordInput.value.length > 0);', source)
        self.assertIn('helperTextContainer__5a838', source)
        self.assertIn('statusMessageContainer__5a838', source)
        self.assertIn('app.add_url_rule("/api/auth/change-email"', app_source)
        self.assertIn('clear_provider_tokens=True', app_source)
        self.assertIn('async function changeEmail(email, password)', auth_source)

    def test_verification_notice_opens_flow_instead_of_direct_resend(self):
        source = (ASSET_UI_JS / "account-verification.js").read_text(encoding="utf-8")
        channels = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        self.assertIn('showVerificationRequired(authProvider);', source)
        self.assertIn('wireVerificationNotice(authProvider, session)', channels)
        self.assertNotIn('authProvider.resendConfirmation()', channels)

    def test_voice_runtime_is_real_webrtc_and_preserves_capture(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        auth_source = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        channels_source = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        voice_source = (ASSET_UI_JS / "voice.js").read_text(encoding="utf-8")
        voice_capture = (ASSET_UI_JS / "voice-capture.js").read_text(encoding="utf-8")
        migration = (PRIV_SUPABASE_MIGRATIONS / "000_current_schema.sql").read_text(encoding="utf-8")

        self.assertIn('microphone=(self)', app_source)
        self.assertIn('camera=()', app_source)
        self.assertIn('app.add_url_rule("/api/voice/join"', app_source)
        self.assertIn('app.add_url_rule("/api/voice/state"', app_source)
        self.assertIn('app.add_url_rule("/api/voice/signal"', app_source)
        self.assertIn('app.add_url_rule("/api/voice/leave"', app_source)
        self.assertIn('Policy.allowed(actor, "voice.connect")', app_source)
        self.assertIn('VOICE_ICE_SERVERS_JSON', app_source)
        self.assertIn('"channels": [{', app_source)
        self.assertIn('"type": str(item.get("channel_type") or "text")', app_source)

        self.assertIn('navigator.mediaDevices.getUserMedia', voice_source)
        self.assertIn('new RTCPeerConnection', voice_source)
        self.assertIn('VOICE_CAPTURE', voice_source)
        self.assertIn('Voice Connected', voice_capture)
        self.assertIn('Welcome to your first voice channel!', voice_capture)
        self.assertIn('list_c3cd7d list__07f91 listDefault__07f91', voice_capture)
        self.assertIn('currentRoundTripTime', voice_source)
        self.assertIn('this.muted = false', voice_source)
        self.assertIn('loadModule("voice")', channels_source)

        self.assertIn('async function joinVoice', auth_source)
        self.assertIn('async function sendVoiceSignal', auth_source)
        self.assertIn('def voice_join', provider_source)
        self.assertIn('def voice_signal', provider_source)
        self.assertIn("AND ch.channel_type = 'voice'", provider_source)
        self.assertIn('len(encoded.encode("utf-8")) > 65536', provider_source)

        self.assertIn('create table if not exists public.voice_sessions', migration)
        self.assertIn('create table if not exists public.voice_signals', migration)
        self.assertIn('force row level security', migration)
        self.assertIn('revoke all on table public.voice_sessions from authenticated', migration)
        self.assertIn('revoke all on table public.voice_signals from authenticated', migration)


    def test_voice_ui_uses_captured_html_only_and_does_not_invent_css_or_svg(self):
        source = (ASSET_UI_JS / "voice.js").read_text(encoding="utf-8")
        capture = (ASSET_UI_JS / "voice-capture.js").read_text(encoding="utf-8")
        self.assertIn('import { VOICE_CAPTURE } from "./voice-capture.js";', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.connectedWrapper)', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.voiceUsersList)', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.channelInfo)', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.accountSubtext)', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.unmutedMicIcon)', source)
        self.assertIn('capturedNode(VOICE_CAPTURE.introLayer)', source)
        self.assertNotIn('function micSvg', source)
        self.assertNotIn('function headsetSvg', source)
        self.assertNotIn('function participantMarkup', source)
        self.assertNotIn('function voicePanelMarkup', source)
        self.assertNotIn('function introMarkup', source)
        self.assertNotIn('document.createElement("div")', source)
        self.assertNotIn('.style.display =', source)
        self.assertNotIn('.style.width =', source)
        self.assertNotIn('.style.height =', source)
        self.assertIn('voicePanelIntroductionWrapper_e131a9 theme-light', capture)
        self.assertIn('rtcConnectionStatusWrapper__06d62', capture)
        self.assertIn('lottieIcon__5eb9b lottieIconColors__5eb9b', capture)
        self.assertIn('voiceUser__07f91', capture)

    def test_voice_capture_source_remains_script_free_and_untouched(self):
        html = (STATIC_PAGES / "guild.html").read_text(encoding="utf-8")
        self.assertNotIn('<script', html.lower())
        self.assertIn('section class="panels__5e434"', html)
        self.assertIn('class="wrapper_e131a9"', html)
        self.assertIn('aria-label="General (canal de voz)"', html)

    def test_application_schema_health_includes_real_friend_request_table(self):
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn("to_regclass('public.friend_requests') IS NOT NULL", provider_source)
        self.assertIn('"friend_requests": bool(row and row[2])', provider_source)
        self.assertIn('DATABASE_SCHEMA_VERSION = "9"', app_source)
        self.assertIn('current-schema-v9', app_source)



    def test_pending_friend_requests_cover_sent_received_accept_ignore_and_delete_cancel(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        auth_source = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        self.assertIn('app.add_url_rule("/api/friends/requests/pending"', app_source)
        self.assertIn('app.add_url_rule("/api/friends/requests/<request_id>/cancel"', app_source)
        self.assertIn('app.add_url_rule("/api/friends/requests/<request_id>/accept"', app_source)
        self.assertIn('app.add_url_rule("/api/friends/requests/<request_id>/ignore"', app_source)
        self.assertIn('Policy.allowed(actor, "friend.request.read")', app_source)
        self.assertIn('Policy.allowed(actor, "friend.request.cancel")', app_source)
        self.assertIn('Policy.allowed(actor, "friend.request.accept")', app_source)
        self.assertIn('Policy.allowed(actor, "friend.request.ignore")', app_source)
        self.assertIn('provider.list_pending_friend_requests(actor.id)', app_source)
        self.assertIn('provider.cancel_outgoing_friend_request(actor.id, request_id)', app_source)
        self.assertIn('provider.accept_incoming_friend_request(actor.id, request_id)', app_source)
        self.assertIn('provider.ignore_incoming_friend_request(actor.id, request_id)', app_source)
        self.assertIn("SELECT 'sent'::text AS direction", provider_source)
        self.assertIn("SELECT 'received'::text AS direction", provider_source)
        self.assertIn('DELETE FROM public.friend_requests', provider_source)
        self.assertIn("SET status = 'accepted', updated_at = now()", provider_source)
        self.assertIn('AND sender_id = %s::uuid', provider_source)
        self.assertIn('AND receiver_id = %s::uuid', provider_source)
        self.assertIn('async function listPendingFriendRequests()', auth_source)
        self.assertIn('async function cancelFriendRequest(requestId)', auth_source)
        self.assertIn('async function acceptFriendRequest(requestId)', auth_source)
        self.assertIn('async function ignoreFriendRequest(requestId)', auth_source)

    def test_pending_navigation_uses_own_people_column_and_original_badge_shape(self):
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        self.assertIn('item__133bf item_aa8da2 themed_aa8da2', source)
        self.assertIn('peopleColumn__133bf', source)
        self.assertIn('peopleListItem_cc6179 text-md/medium_cc6179', source)
        self.assertIn('actionAccept_f8fa06', source)
        self.assertIn('actionDeny_f8fa06', source)
        self.assertIn('tooltip_c36707 tooltipPrimary_c36707 tooltipBottom_c36707', source)
        self.assertIn('tabBar.insertBefore(pendingTab, addTab)', source)
        self.assertIn('pendingPanel?.isConnected) pendingPanel.replaceWith(addPanel)', source)
        self.assertIn('addPanel.isConnected) addPanel.replaceWith(next)', source)
        self.assertNotIn('addPanel.hidden = true', source)
        self.assertIn('buildSection("Recebidos", state.received, "received", handlers)', source)
        self.assertIn('buildSection("Enviados", state.sent, "sent", handlers)', source)
        self.assertIn('classes.push("badge__133bf")', source)
        self.assertIn('text.appendChild(numberBadge(incomingCount, { tab: true }))', source)
        self.assertIn('friendsButtonContainer_e6b769 a.link__972a0', source)
        self.assertIn('link.appendChild(numberBadge(incomingCount', source)
        self.assertIn('state.received.length', source)
        self.assertIn('DEFAULT_AVATAR', source)
        self.assertNotIn('slide.animate([', source)

    def test_pending_badge_counts_only_received_requests_and_refreshes_other_sessions(self):
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        self.assertIn('const incomingCount = () => state.received.length;', source)
        self.assertIn('syncFriendsSidebarBadge(incoming);', source)
        self.assertNotIn('window.setInterval(', source, "friend state must not use periodic network polling")
        self.assertIn('window.addEventListener("focus", onFocus)', source)
        self.assertIn('document.addEventListener("visibilitychange", onVisibility)', source)
        self.assertIn('activePendingController?.stop?.()', source)
        self.assertIn('window.removeEventListener("focus", onFocus)', source)

    def test_pending_panel_does_not_duplicate_now_playing_column(self):
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        self.assertIn('const nowPlaying = tabBody?.querySelector(".nowPlayingColumn__133bf")', source)
        self.assertIn('tabBody.insertBefore(next, nowPlaying)', source)
        self.assertNotIn('refresh-active-now', source)


    def test_pending_notifications_are_server_hydrated_before_first_paint(self):
        app_source = web_source()
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        route = (WEB_LIB / 'controllers' / 'guilds.py').read_text(encoding='utf-8')
        self.assertIn('provider.list_pending_friend_requests(actor.id)', route)
        self.assertIn('_hydrate_friend_pending_shell(html, friend_requests', route)
        self.assertLess(route.index('provider.list_pending_friend_requests(actor.id)'), route.index('loader ='))
        self.assertIn('id="app-friend-pending-bootstrap"', app_source)
        self.assertIn('type="application/json"', app_source)
        self.assertIn('data-app-pending-tab="true"', app_source)
        self.assertIn('data-app-friend-incoming-badge="true"', app_source)
        self.assertIn('const bootstrap = readPendingBootstrap();', source)
        self.assertIn('if (bootstrap) {', source)
        self.assertIn('syncNavigation();', source)
        self.assertIn('wirePendingTab();', source)
        self.assertIn('if (parsed.ready === false) return null;', source)

    def test_pending_action_tooltips_have_one_shared_state(self):
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        self.assertIn('const ActionTooltip = (() => {', source)
        self.assertEqual(source.count('let tooltip = null;'), 1)
        self.assertIn('if (expectedAnchor && anchor !== expectedAnchor) return;', source)
        self.assertIn('ActionTooltip.show(button, label)', source)
        self.assertIn('ActionTooltip.hide(button)', source)
        self.assertIn('data-app-action-tooltip', source)
        self.assertIn('if (stale !== tooltip) stale.remove();', source)
        wire_block = source[source.index('function wireActionTooltip'):source.index('function readPendingBootstrap')]
        self.assertNotIn('let tooltip = null', wire_block)

    def test_direct_message_close_uses_original_hover_button_and_persists_closed_row(self):
        source = (ASSET_UI_JS / "direct-messages.js").read_text(encoding="utf-8")
        channels_source = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('.closeButton__972a0[role="button"]', source)
        self.assertIn("li.dm__972a0.channel__972a0", source)
        self.assertIn("removeConversationProjections(id, row);", source)
        self.assertIn('document.getElementById("guild-list-unread-dms")', source)
        self.assertIn('guildsnav___${entityId}', source)
        self.assertIn("unreadDmTile(entityId)?.remove();", source)
        self.assertIn("localStorage.setItem", source)
        self.assertIn("storageKeyForUser(user)", source)
        self.assertIn('event.key !== "Enter" && event.key !== " "', source)
        self.assertIn('loadModule("direct-messages")', channels_source)
        self.assertIn("wireDirectMessageCloseButtons(session.user);", channels_source)
        self.assertIn('"direct-messages.js"', app_source)

    def test_session_authority_cookie_liveness_and_fast_watchdog_are_consolidated(self):
        app_source = web_source()
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        storage_source = (APP_LIB / "storage.py").read_text(encoding="utf-8")
        authority = (APP_LIB / "session_authority.py").read_text(encoding="utf-8")
        security = (APP_LIB / "security.py").read_text(encoding="utf-8")
        watchdog = (ASSET_UI_JS / "session-watchdog.js").read_text(encoding="utf-8")
        channels = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        auth_provider = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")

        self.assertIn("def auth_user_exists_by_id", provider_source)
        self.assertIn("deleted_at IS NULL", provider_source)
        self.assertIn("def delete_browser_sessions_for_user", storage_source)
        self.assertIn("BROWSER_SESSION_VERSION = 2", storage_source)
        self.assertIn('APP_PRESENCE_COOKIE = "app_presence"', app_source)
        self.assertIn("keys.presence_for_session(raw)", app_source)
        self.assertIn("constant_equal(presence, expected)", app_source)
        self.assertIn("def presence_for_session", security)
        self.assertIn("session_authority.user_exists(actor.id)", app_source)
        self.assertIn("session_authority.revoke_user(user_id)", app_source)
        self.assertIn('app.add_url_rule("/api/session/validate"', app_source)
        self.assertNotIn('app.add_url_rule("/api/session/validate", view_func=api_session_validate, methods=["POST"]', app_source)

        self.assertIn("class SessionAuthority", authority)
        self.assertIn("lease_seconds: float = 0.75", authority)
        self.assertIn("self._inflight", authority)
        self.assertIn("threading.Event()", authority)
        self.assertIn("event.wait(timeout=3.0)", authority)

        self.assertIn('const PRESENCE_COOKIE = "app_presence";', watchdog)
        self.assertIn('const SESSION_CHANNEL = "app-session-events";', watchdog)
        self.assertNotIn("PRESENCE_POLL_MS", watchdog)
        self.assertNotIn("NETWORK_HEARTBEAT_MS", watchdog)
        self.assertNotIn("setInterval(", watchdog, "session liveness must be event-driven, not polled")
        self.assertIn('window.cookieStore?.addEventListener?.("change"', watchdog)
        self.assertIn('window.addEventListener("focus", onActivity)', watchdog)
        self.assertIn('window.addEventListener("pageshow", onActivity)', watchdog)
        self.assertIn('window.addEventListener("online", onActivity)', watchdog)
        self.assertIn("new BroadcastChannel(SESSION_CHANNEL)", watchdog)
        self.assertIn('location.replace(appUrl("login.html"))', watchdog)
        self.assertIn('loadModule("session-watchdog")', channels)
        self.assertIn("wireSessionWatchdog(authProvider);", channels)
        self.assertIn('get("/api/session/validate")', auth_provider)
        self.assertNotIn('post("/api/session/validate", {})', auth_provider)

    def test_session_reads_are_pure_and_database_connections_are_pooled(self):
        storage_source = (APP_LIB / "storage.py").read_text(encoding="utf-8")
        provider_source = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        get_session = storage_source[storage_source.index("    def get_browser_session"):storage_source.index("    def authenticate_browser_session")]
        self.assertNotIn("UPDATE browser_sessions SET last_seen_at", get_session)
        self.assertIn("Session reads are deliberately side-effect free", get_session)
        self.assertIn("LifoQueue(maxsize=4)", provider_source)
        self.assertIn("def _database_connection", provider_source)
        self.assertEqual(provider_source.count("conn = psycopg.connect("), 1, "all DB operations must pass through the bounded pool")

    def test_authenticated_shell_uses_server_bootstrap_before_runtime_wiring(self):
        app_source = web_source()
        channels = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        self.assertIn("def _session_bootstrap_html", app_source)
        self.assertIn('id="app-session-bootstrap"', app_source)
        self.assertIn("session_bootstrap = _session_bootstrap_html(actor, row)", app_source)
        self.assertIn("readSessionBootstrap", channels)
        self.assertIn("const session = await resolveSession(authProvider);", channels)
        self.assertNotIn("await authProvider.verificationStatus()", channels)
        self.assertIn('response.headers["Server-Timing"] = f"session;dur={identity_ms:.2f}, friends;dur={friend_ms:.2f}, guilds;dur={guild_ms:.2f}"', app_source)
        self.assertIn('response.headers["Server-Timing"] = f"session;dur=', app_source)

    def test_pending_tab_badge_has_explicit_16px_centering_without_css_file_change(self):
        source = (ASSET_UI_JS / "friend-pending.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('badge.style.height = "16px";', source)
        self.assertIn('badge.style.minWidth = "16px";', source)
        self.assertIn('badge.style.alignItems = "center";', source)
        self.assertIn('badge.style.justifyContent = "center";', source)
        self.assertIn('badge.style.lineHeight = "16px";', source)
        self.assertIn('" height: 16px; min-width: 16px; box-sizing: border-box; "', app_source)
        self.assertIn('"display: flex; align-items: center; justify-content: center; line-height: 16px;"', app_source)



    def test_guild_creation_flow_is_three_steps_one_state_and_one_customize_implementation(self):
        source = (ASSET_UI_JS / "server-entry.js").read_text(encoding="utf-8")
        auth = (ASSET_JS / "auth-provider.js").read_text(encoding="utf-8")
        channels = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        runtime = (ASSET_UI_JS / "runtime.js").read_text(encoding="utf-8")
        self.assertIn('data-app-server-template="custom"', source)
        self.assertIn('data-app-server-template="gaming"', source)
        self.assertIn('data-app-server-template="friends"', source)
        self.assertIn('data-app-server-template="study_group"', source)
        self.assertIn('data-app-server-template="school_club"', source)
        self.assertIn('data-app-server-template="local_community"', source)
        self.assertIn('data-app-server-template="artists_creators"', source)
        self.assertIn('data-app-server-audience="friends"', source)
        self.assertIn('data-app-server-audience="community"', source)
        self.assertIn('data-app-server-audience="skipped"', source)
        self.assertEqual(source.count('function customizeStepMarkup('), 1)
        self.assertIn('Conte-nos mais sobre seu servidor', source)
        self.assertIn('Personalize seu servidor', source)
        self.assertIn('header__78f69', source)
        self.assertIn('header_b917ac', source)
        self.assertIn('createGuild_b917ac', source)
        self.assertIn('uploadIcon_b917ac', source)
        self.assertIn('data-app-create-server-back="templates"', source)
        self.assertIn('data-app-create-server-back="audience"', source)
        self.assertIn('state.name = input.value.trim();', source)
        self.assertIn('setButtonBusy(submit, true)', source)
        self.assertIn('async function createGuild({ name, templateKey, audience, icon = null })', auth)
        self.assertIn('const form = new FormData();', auth)
        self.assertNotIn('"Content-Type": "multipart/form-data"', auth)
        self.assertIn('loadModule("server-entry")', channels)
        self.assertIn('export function setButtonBusy(button, busy)', runtime)


    def test_join_server_modal_reuses_captured_hierarchy_and_shared_slide_state(self):
        source = (ASSET_UI_JS / "server-entry.js").read_text(encoding="utf-8")
        self.assertIn('join: 458', source)
        self.assertIn('data-app-join-server-open="true"', source)
        self.assertIn('function joinServerStepMarkup(', source)
        self.assertEqual(source.count('function joinServerStepMarkup('), 1)
        self.assertIn('header__991a0', source)
        self.assertIn('inputForm__991a0', source)
        self.assertIn('sampleLinks__991a0', source)
        self.assertIn('rowContainer__991a0', source)
        self.assertIn('footer__991a0', source)
        self.assertIn('data-app-join-server-form="true"', source)
        self.assertIn('data-app-join-server-submit="true"', source)
        self.assertIn('render("join", "forward")', source)
        self.assertIn('render("templates", "back")', source)
        self.assertIn('animateStep(slide, direction)', source)
        self.assertIn('state.joinInvite', source)
        self.assertNotIn('fetch("https://discord.gg/', source)

    def test_guild_schema_is_real_postgresql_default_deny_and_member_scoped(self):
        migration = (PRIV_SUPABASE_MIGRATIONS / "000_current_schema.sql").read_text(encoding="utf-8").lower()
        provider = (APP_LIB / "supabase_service.py").read_text(encoding="utf-8")
        app = web_source()
        access = (APP_LIB / "access.py").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.guilds", migration)
        self.assertIn("create table if not exists public.guild_members", migration)
        self.assertIn("create table if not exists public.guild_channels", migration)
        self.assertIn("references auth.users(id) on delete cascade", migration)
        self.assertIn("enable row level security", migration)
        self.assertIn("force row level security", migration)
        self.assertIn("revoke all on table public.guilds from authenticated", migration)
        self.assertIn("def create_guild(", provider)
        self.assertIn("def list_user_guilds(", provider)
        self.assertIn("def get_guild_channel_for_user(", provider)
        self.assertIn("FROM public.guild_members", provider)
        self.assertIn("gm.user_id = %s::uuid", provider)
        self.assertIn('app.add_url_rule("/api/guilds"', app)
        self.assertIn('Policy.allowed(actor, "guild.create")', app)
        self.assertIn('app.add_url_rule("/channels/<guild_id>/<channel_id>"', app)
        self.assertIn('Policy.allowed(actor, "guild.read")', app)
        self.assertIn('"guild.create"', access)
        self.assertIn('"guild.read"', access)

    def test_server_capture_is_unified_and_media_delivery_is_externalized(self):
        guild_css = (ASSET_CSS / "guild.css").read_text(encoding="utf-8")
        guild_html = (STATIC_PAGES / "guild.html").read_text(encoding="utf-8")
        app_source = web_source()
        cloud_source = (APP_LIB / "cloudinary_service.py").read_text(encoding="utf-8")
        self.assertTrue(guild_css.startswith('@import url("channels.css");'))
        self.assertIn('<html lang="pt-BR"', guild_html)
        self.assertNotIn('<script', guild_html)
        self.assertIn('__APP_GUILD_NAME__', guild_html)
        self.assertIn('__APP_GUILD_ID__', guild_html)
        self.assertNotIn('drag-previewer', guild_html)
        self.assertNotIn('contain: paint', guild_html)
        self.assertIn('pointerEvents__44b0c', guild_html)
        self.assertNotIn('pointerEventos__44b0c', guild_html)
        self.assertIn('app.add_url_rule("/images/<path:filename>"', app_source)
        self.assertIn('cloudinary.delivery_url(canonical)', app_source)
        self.assertIn('"0085-og_img_discord_home.png": "0084-og_img_discord_home.png"', app_source)
        self.assertIn('https://res.cloudinary.com/', cloud_source)

    def test_created_guild_becomes_selected_sidebar_item_before_add_discover_download(self):
        app = web_source()
        nav = (ASSET_UI_JS / "guild-navigation.js").read_text(encoding="utf-8")
        channels = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        self.assertIn('class="blobContainer_e5445c{selected_blob}"', app)
        self.assertIn('selected__6e9f8', app)
        self.assertIn('acronym__6e9f8', app)
        self.assertIn("_guild_acronym(name)", app)
        self.assertIn('marker = \'<div class="tutorialContainer__650eb">\'', app)
        self.assertIn('data-app-guild-id=', app)
        self.assertIn('[data-app-guild-id][data-app-guild-channel-id]', nav)
        self.assertNotIn('"X-App-SPA": "1"', nav)
        self.assertNotIn('history.pushState({ appSpa: true }', nav)
        self.assertNotIn('importReplacement(parsed, ".sidebarList__5e434")', nav)
        self.assertNotIn('importReplacement(parsed, ".page__5e434")', nav)
        self.assertNotIn('updatePersistentGuildRail(path, guild)', nav)
        self.assertIn('location.assign(target);', nav)
        self.assertIn('wireGuildNavigation();', channels)
        self.assertIn('spa_partial = request.headers.get("X-App-SPA", "") == "1"', app)
        self.assertIn('provider.get_guild_view_for_user(actor.id, guild_id, channel_id)', app)
        self.assertIn('guilds = [] if spa_partial else provider.list_user_guilds(actor.id)', app)
        self.assertIn('guild.css', app)
        self.assertIn('guild.html', app)


    def test_browser_module_allowlist_covers_all_frontend_modules(self):
        app_source = web_source()
        block = re.search(r"UI_MODULE_FILES\s*=\s*frozenset\(\{(.*?)\}\)", app_source, re.S)
        self.assertIsNotNone(block)
        allowed = set(re.findall(r'"([^"]+\.js)"', block.group(1)))
        frontend = {path.name for path in ASSET_UI_JS.glob("*.js")}
        self.assertEqual(frontend, allowed)
        self.assertIn("voice-capture.js", allowed)

    def test_page_bootstrap_loads_only_route_specific_modules(self):
        source = (ASSET_UI_JS / "bootstrap.js").read_text(encoding="utf-8")
        self.assertIn('if (State.page === "login") await bootLogin()', source)
        self.assertIn('else if (State.page === "register") await bootRegister()', source)
        self.assertIn('else if (State.page === "channels") await bootChannels()', source)
        self.assertIn('import("./login.js")', source)
        self.assertIn('import("./register-validation.js")', source)
        self.assertIn('import("./date-menu.js")', source)
        self.assertIn('import("./channels.js")', source)
        # Registration-only UI must never be a static dependency of login.
        self.assertNotIn('from "./date-menu.js"', source)
        self.assertNotIn('from "./register-validation.js"', source)
        self.assertNotIn('from "./register-form.js"', source)

    def test_authenticated_heavy_features_are_loaded_on_demand(self):
        source = (ASSET_UI_JS / "channels.js").read_text(encoding="utf-8")
        self.assertNotIn('from "./server-entry.js"', source)
        self.assertNotIn('from "./voice.js"', source)
        self.assertIn('loadModule("server-entry")', source)
        self.assertIn('loadModule("voice")', source)
        self.assertIn('input[name="add-friend"]', source)

    def test_auth_forms_fail_closed_before_page_specific_javascript_boots(self):
        ui = (ASSET_JS / "ui.js").read_text(encoding="utf-8")
        app_source = web_source()
        self.assertIn('document.addEventListener("submit"', ui)
        self.assertIn('input[type="password"]', ui)
        self.assertIn('if (method === "get") event.preventDefault();', ui)
        self.assertIn("def strip_auth_query_credentials", app_source)
        self.assertIn("SENSITIVE_AUTH_QUERY_KEYS", app_source)
        self.assertLess(
            app_source.index("def strip_auth_query_credentials"),
            app_source.index("def reject_untrusted_host"),
        )


    def test_frontend_has_no_html_assignment_or_code_generation_sinks(self):
        patterns = (
            "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write",
            "eval(", "new Function",
        )
        js_files = [ASSET_JS / "ui.js", ASSET_JS / "auth-provider.js", *ASSET_UI_JS.glob("*.js")]
        for path in js_files:
            source = path.read_text(encoding="utf-8")
            for pattern in patterns:
                self.assertNotIn(pattern, source, f"{pattern} em {path.name}")
        dom_source = (ASSET_UI_JS / "dom.js").read_text(encoding="utf-8")
        self.assertIn("new DOMParser()", dom_source)
        self.assertIn("document.createDocumentFragment()", dom_source)

    def test_repository_cleanup_rules_are_enforced(self):
        markdown = sorted(
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*.md")
            if not any(part in GENERATED_TREE_PARTS for part in path.relative_to(ROOT).parts)
        )
        self.assertEqual(markdown, ["README.md"])
        sql_files = sorted(
            path.relative_to(ROOT).as_posix()
            for path in ROOT.rglob("*.sql")
            if not any(part in GENERATED_TREE_PARTS for part in path.relative_to(ROOT).parts)
        )
        self.assertEqual(sql_files, ["priv/supabase/migrations/000_current_schema.sql"])
        self.assertFalse((ROOT / "source-manifests").exists())
        self.assertFalse((PRIV_ARCH / "asset-manifest.json").exists())
        self.assertFalse((PRIV_ARCH / "server-capture-manifest.json").exists())
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if (
                not path.is_file()
                or path.name == "SUPABASE_PRIVILEGED.env"
                or any(part in GENERATED_TREE_PARTS for part in relative.parts)
                or path.suffix.lower() in {".pyc", ".pyo"}
            ):
                continue
            if path.suffix.lower() in {".html", ".css", ".woff2", ".png", ".webp", ".svg"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for forbidden in ("SEC" + "573", "FOR" + "578", "FOR" + "589"):
                self.assertNotIn(forbidden, text, path.as_posix())
            self.assertNotIn("hide" + "01", text.lower(), path.as_posix())

    def test_private_bootstrap_and_admin_store_contract_include_current_providers(self):
        bootstrap = (APP_LIB / "bootstrap.py").read_text(encoding="utf-8")
        cloud = (APP_LIB / "cloudinary_service.py").read_text(encoding="utf-8")
        private_env = ROOT / "config" / "SUPABASE_PRIVILEGED.env"
        public_contract = ROOT / "config" / ".env.example"
        env_path = private_env if private_env.is_file() else public_contract
        self.assertTrue(env_path.is_file(), "provider configuration contract is missing")
        names = set()
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            names.add(line.split("=", 1)[0])
        for required in {
            "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_LEGACY_ANON_KEY",
            "SUPABASE_JWT_LEGACY_SECRET", "SUPABASE_JWKS_URL", "SUPABASE_JWKS_KID",
            "SUPABASE_JWKS_PREVIOUS_KID", "SUPABASE_JWKS_STATIC_JSON",
            "SUPABASE_PROJECT_REF", "SUPABASE_DB_HOST", "SUPABASE_DB_PASSWORD", "HCAPTCHA_SITE_KEY",
            "HCAPTCHA_SECRET", "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY",
            "CLOUDINARY_API_SECRET", "CLOUDINARY_FOLDER",
        }:
            self.assertIn(required, names)
            self.assertIn(f'"{required}"', bootstrap)
        self.assertIn("SUPABASE_DB_PASSWORD", names)
        self.assertIn("def save_partial", cloud)
        self.assertIn("def test_connection", cloud)
        self.assertIn("def migrate_directory", cloud)
        security = (APP_LIB / "security.py").read_text(encoding="utf-8")
        storage = (APP_LIB / "storage.py").read_text(encoding="utf-8")
        self.assertIn("Fernet.generate_key()", security)
        self.assertIn("CREATE TABLE IF NOT EXISTS secure_settings", storage)

    def test_authentication_surfaces_do_not_expose_email_existence(self):
        app_source = web_source()
        login = app_source[app_source.index('def api_login():'):app_source.index('def api_login_link():')]
        recovery = app_source[app_source.index('def api_login_link():'):app_source.index('def _username_candidate_base', app_source.index('def api_login_link():'))]
        frontend = (ASSET_UI_JS / "login.js").read_text(encoding="utf-8")
        self.assertNotIn("provider.auth_email_exists(identifier)", login)
        self.assertNotIn('"code": "email_not_found"', login)
        self.assertNotIn("provider.auth_email_exists(identifier)", recovery)
        self.assertIn("Se a conta existir e estiver apta", recovery)
        self.assertNotIn("email_not_found", frontend)

    def test_host_header_is_canonical_and_hcaptcha_does_not_override_siteverify(self):
        app_source = web_source()
        captcha_source = (APP_LIB / "hcaptcha_service.py").read_text(encoding="utf-8")
        local_config = ROOT / "config" / ".env"
        public_contract = ROOT / "config" / ".env.example"
        config_path = local_config if local_config.is_file() else public_contract
        config = config_path.read_text(encoding="utf-8")
        self.assertIn("def reject_untrusted_host", app_source)
        self.assertIn('ALLOWED_HOSTS = frozenset({APP_HOSTNAME})', app_source)
        self.assertIn('APP_HOSTNAME=discord', config)
        self.assertIn('success = bool(data.get("success"))', captcha_source)
        self.assertIn('hostname = str(data.get("hostname") or "")', captcha_source)
        self.assertNotIn("hostname-mismatch", captcha_source)
        self.assertNotIn("hostname_allowed(", captcha_source)

    def test_password_policy_is_shared_and_strong(self):
        validators = (APP_LIB / "validators.py").read_text(encoding="utf-8")
        app_source = web_source()
        register = (ASSET_UI_JS / "register-form.js").read_text(encoding="utf-8")
        self.assertIn("PASSWORD_MIN_LENGTH = 16", validators)
        self.assertIn("validate_password_strength(raw_password", validators)
        self.assertIn('validate_password_strength(request.form.get("password")', app_source)
        self.assertFalse((PRIV_SCRIPTS / "install_admin.py").exists())
        self.assertIn("password.length < 16", register)

    def test_registration_readiness_distinguishes_provider_database_and_schema(self):
        app_source = web_source()
        start = app_source.index("def registration_readiness_error")
        end = app_source.index("SUPABASE_URL_RE", start)
        block = app_source[start:end]
        self.assertIn('"code": "not_configured"', block)
        self.assertIn('"code": "database_not_configured"', block)
        self.assertIn('"code": "schema_not_ready"', block)
        self.assertLess(block.index('"code": "database_not_configured"'), block.index('"code": "schema_not_ready"'))


    def test_cloudinary_admin_backend_exists_without_modifying_admin_html(self):
        app_source = web_source()
        self.assertIn('app.add_url_rule("/admin/cloudinary/status"', app_source)
        self.assertIn('app.add_url_rule("/admin/cloudinary/config"', app_source)
        self.assertIn('app.add_url_rule("/admin/cloudinary/test"', app_source)
        self.assertIn('app.add_url_rule("/admin/cloudinary/migrate-images"', app_source)
        self.assertIn("require_admin_csrf()", app_source)
        self.assertIn('CLOUDINARY_IMPORT_DIR = INSTANCE_DIR / "cloudinary-import"', app_source)
        self.assertIn('source_dir = CLOUDINARY_IMPORT_DIR if CLOUDINARY_IMPORT_DIR.is_dir()', app_source)
        self.assertFalse((ROOT / "priv" / "static" / "images").exists())



    def test_web_app_entrypoint_is_thin_and_routes_are_decomposed_by_controller(self):
        app_source = (WEB_LIB / "app.py").read_text(encoding="utf-8")
        router_source = (WEB_LIB / "router.py").read_text(encoding="utf-8")
        self.assertLess(len(app_source.encode("utf-8")), 5000)
        self.assertIn("def create_app()", app_source)
        self.assertIn("register_routes(app)", app_source)
        self.assertNotIn("def api_login", app_source)
        self.assertNotIn("def admin_config", app_source)
        for rel in [
            "controllers/pages.py", "controllers/guilds.py", "controllers/voice.py",
            "controllers/friends.py", "controllers/assets.py",
            "controllers/auth/login.py", "controllers/auth/registration.py",
            "controllers/auth/session.py", "controllers/admin/config.py",
            "controllers/admin/database.py", "controllers/admin/users.py",
        ]:
            self.assertTrue((WEB_LIB / rel).is_file(), rel)
        self.assertIn("ROUTE_MODULES", router_source)

    def test_local_hostname_installer_is_unique_logged_and_fail_closed(self):
        script = (PRIV_SCRIPTS / "ensure_local_hostname.ps1").read_text(encoding="utf-8")
        installer = (ROOT / "INSTALL_HCAPTCHA_HOST.bat").read_text(encoding="utf-8")
        self.assertIn('$hostname = "discord"', script)
        self.assertIn("Test-CanonicalMapping", script)
        self.assertIn("Get-CurrentPowerShellExecutable", script)
        self.assertIn("Start-Process -FilePath $powershellExe -Verb RunAs", script)
        self.assertNotIn('Start-Process -FilePath "powershell.exe" -Verb RunAs', script)
        self.assertIn("hostname-setup.log", script)
        self.assertIn("[System.IO.File]::WriteAllLines", script)
        self.assertIn("127.0.0.1`tdiscord", script)
        self.assertIn("Diagnostico:", installer)
        self.assertNotIn("discord" + ".local" + ".test", script)


if __name__ == "__main__":
    unittest.main()

class ElixirLayoutAndVoiceAudioTests(unittest.TestCase):
    def test_source_tree_matches_phoenix_style_top_level(self):
        for name in ("assets", "config", "lib", "priv", "test"):
            self.assertTrue((ROOT / name).is_dir(), name)
        for obsolete in ("core", "frontend", "fonts", "templates", "tests", "architecture", "supabase", "scripts"):
            self.assertFalse((ROOT / obsolete).exists(), obsolete)
        self.assertTrue((ROOT / "lib" / "discord_app").is_dir())
        self.assertTrue((ROOT / "lib" / "discord_app_web").is_dir())

    def test_voice_control_audio_is_logical_state_not_icon_dependent(self):
        sounds = (ASSET_UI_JS / "voice-sounds.js").read_text(encoding="utf-8")
        voice = (ASSET_UI_JS / "voice.js").read_text(encoding="utf-8")
        for marker in (
            "529ff198eac567af_nhesmn.mp3",
            "b150f03c89944403_qvpaen.mp3",
            "2d3b4ba32c34c862_ooopar.mp3",
            "e74c4a06134a20e4_kzqukf.mp3",
        ):
            self.assertIn(marker, sounds)
        self.assertIn("setMicrophoneMuted", voice)
        self.assertIn("setHeadphonesMuted", voice)
        self.assertIn('window.addEventListener("app:voice-control"', voice)
        self.assertIn("voiceControlSoundboard.microphone", voice)
        self.assertIn("voiceControlSoundboard.headphone", voice)
