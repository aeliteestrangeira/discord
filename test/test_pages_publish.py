from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PagesPublishTests(unittest.TestCase):
    def test_pages_build_uses_canonical_app_without_landing(self):
        with tempfile.TemporaryDirectory(prefix="discord-pages-test-") as tmp:
            output = Path(tmp) / "site"
            subprocess.run(
                [sys.executable, str(ROOT / "priv/scripts/build_pages.py"), "--output", str(output)],
                cwd=ROOT,
                check=True,
            )
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("Boas-vindas de volta!", index)
            self.assertIn('href="discord.css"', index)
            self.assertRegex(index, r'src="runtime/[a-f0-9]{16}/ui\.js"')
            self.assertNotIn("O mesmo site, agora em aplicativo desktop.", index)
            self.assertNotIn("WINDOWS DESKTOP", index)
            self.assertTrue((output / "register.html").is_file())
            self.assertTrue((output / "channels.html").is_file())
            self.assertTrue((output / "guild.html").is_file())
            channels_html = (output / "channels.html").read_text(encoding="utf-8")
            guild_html = (output / "guild.html").read_text(encoding="utf-8")
            self.assertRegex(channels_html, r'<script src="runtime/[a-f0-9]{16}/ui\.js" defer></script>')
            self.assertNotIn('src="runtime/', (ROOT / "priv/static/pages/channels.html").read_text(encoding="utf-8"))
            self.assertIn('href="channels.css"', channels_html)
            self.assertNotIn('href="/channels.css"', channels_html)
            self.assertIn('href="guild.css"', guild_html)
            self.assertNotIn('href="/guild.css"', guild_html)
            self.assertTrue((output / "channels.css").is_file())
            self.assertTrue((output / "guild.css").is_file())
            self.assertTrue((output / "images/0206-c6a249645d46209f337279cd2ca998c7.webp").is_file())
            self.assertTrue((output / "images/0207-c6a249645d46209f337279cd2ca998c7.webp").is_file())
            self.assertTrue((output / "images/0208-2ccd8ae8b2379360.png").is_file())
            self.assertTrue((output / "images/0210-25c27c1328c986f6.svg").is_file())
            self.assertNotIn('src="/images/', channels_html)
            referenced_images = set(re.findall(r'images/([^"\')]+)', channels_html))
            referenced_images.update(re.findall(r'images/([^"\')]+)', (output / "channels.css").read_text(encoding="utf-8")))
            self.assertEqual(len(referenced_images), 150)
            for name in referenced_images:
                self.assertTrue((output / "images" / name).is_file(), name)
            self.assertTrue((output / "admin/index.html").is_file())
            self.assertTrue((output / "ui/bootstrap.js").is_file())
            runtime_dirs = [path for path in (output / "runtime").iterdir() if path.is_dir()]
            self.assertEqual(len(runtime_dirs), 1)
            self.assertTrue((runtime_dirs[0] / "ui.js").is_file())
            self.assertTrue((runtime_dirs[0] / "ui/state.js").is_file())
            self.assertTrue((runtime_dirs[0] / "captcha.css").is_file())
            self.assertTrue((output / "auth-provider.js").is_file())
            self.assertTrue((output / "cloud-runtime.js").is_file())
            self.assertTrue((output / "admin.js").is_file())
            self.assertTrue((output / "admin-web.css").is_file())
            cloud_runtime = (output / "cloud-runtime.js").read_text(encoding="utf-8")
            self.assertIn("aeliteestrangeira.github.io", cloud_runtime)
            self.assertIn("@supabase/supabase-js@2.112.3/dist/umd/supabase.js", cloud_runtime)
            self.assertNotIn("supabase.min.js", cloud_runtime)
            self.assertNotIn("sb_secret_", cloud_runtime)
            self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", cloud_runtime)
            self.assertIn("adminGate", cloud_runtime)
            self.assertIn("getAuthenticatorAssuranceLevel", cloud_runtime)
            self.assertIn("challengeAndVerify", cloud_runtime)
            self.assertIn("exchangeCodeForSession(authCode)", cloud_runtime)
            self.assertIn('searchParams.delete("code")', cloud_runtime)
            admin_html = (output / "admin/index.html").read_text(encoding="utf-8")
            admin_js = (output / "admin.js").read_text(encoding="utf-8")
            self.assertIn("Painel administrativo", admin_html)
            self.assertIn('http-equiv="Content-Security-Policy"', admin_html)
            self.assertNotIn("service_role", admin_html)
            self.assertNotIn("service_role", admin_js)
            self.assertTrue((output / "captcha.css").is_file())
            self.assertTrue((output / "fonts").is_dir())
            self.assertTrue((output / "assets").is_dir())
            self.assertIn("https://res.cloudinary.com/do7vwsnpg/", index)

            info = json.loads((output / "BUILD_INFO.json").read_text(encoding="utf-8"))
            self.assertEqual(info["artifact"], "github-pages-direct-app")
            for name, digest in info["frozenSourceSha256"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)

            manifest = (output / "PAGES_SHA256.txt").read_text(encoding="utf-8").splitlines()
            self.assertGreater(len(manifest), 60)
            for line in manifest:
                digest, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest, name)

    def test_pages_workflow_builds_generated_artifact(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn('python -m unittest discover -s test -p "test_pages_publish.py" -v', workflow)
        self.assertNotIn("python -m unittest test.test_pages_publish", workflow)
        self.assertIn("python priv/scripts/build_pages.py --output _site", workflow)
        self.assertIn("path: _site", workflow)
        self.assertIn('"assets/js/**"', workflow)
        self.assertNotIn("path: site", workflow)

    def test_old_landing_is_removed_from_repository(self):
        for relative in ["site/index.html", "site/site.css", "site/site.js", "site/.nojekyll"]:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_desktop_architecture_accepts_generated_pages_instead_of_legacy_site(self):
        desktop_test = (ROOT / "test/test_desktop.py").read_text(encoding="utf-8")
        self.assertNotIn('"site/index.html", "site/site.css", "site/site.js"', desktop_test)
        self.assertNotIn("test_pages_site_has_no_login_form", desktop_test)
        self.assertIn("test_pages_publish_is_generated_from_canonical_app", desktop_test)
        preflight = (ROOT / "priv/scripts/preflight.py").read_text(encoding="utf-8")
        self.assertIn('import(new URL("ui/bootstrap.js", appRoot).href)', preflight)
        self.assertIn('new URL("../assets/a1c385fb82c39bab.svg", import.meta.url).href', preflight)
        self.assertNotIn('import("/ui/bootstrap.js")', preflight)

    def test_project_pages_base_path_is_resolved_without_touching_frozen_html(self):
        ui = (ROOT / "assets/js/ui.js").read_text(encoding="utf-8")
        runtime = (ROOT / "assets/js/ui/runtime.js").read_text(encoding="utf-8")
        state = (ROOT / "assets/js/ui/state.js").read_text(encoding="utf-8")
        captcha = (ROOT / "assets/js/ui/captcha.js").read_text(encoding="utf-8")
        self.assertIn('const appRoot = new URL("./", currentScript?.src || location.href);', ui)
        self.assertIn('import(new URL("ui/bootstrap.js", appRoot).href)', ui)
        self.assertIn('const MODULE_ROOT_URL = new URL("../", import.meta.url);', runtime)
        self.assertIn('new URL("../../", MODULE_ROOT_URL)', runtime)
        self.assertIn('script.src = new URL("auth-provider.js", APP_ROOT_URL).href;', runtime)
        self.assertIn("location.assign(appUrl(target));", runtime)
        self.assertIn('const moduleRootUrl = new URL("../", import.meta.url);', state)
        self.assertIn('new URL("../../", moduleRootUrl)', state)
        self.assertIn('routeName === "channels.html"', state)
        self.assertIn('initialPath.startsWith("/channels/")', state)
        self.assertIn('link.href = new URL("../captcha.css", import.meta.url).href;', captcha)

    def test_magic_link_callback_is_exchanged_and_redirected(self):
        cloud_runtime = (ROOT / "assets/js/cloud-runtime.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "assets/js/ui/bootstrap.js").read_text(encoding="utf-8")
        self.assertIn('const authCode = String(callbackUrl.searchParams.get("code")', cloud_runtime)
        self.assertIn("detectSessionInUrl: false", cloud_runtime)
        self.assertIn("exchangeCodeForSession(authCode)", cloud_runtime)
        self.assertIn('history.replaceState(history.state, "",', cloud_runtime)
        self.assertIn('new URL(location.href).searchParams.has("code")', bootstrap)
        self.assertIn('location.replace("channels.html")', bootstrap)

    def test_channels_redirects_remain_inside_project_pages(self):
        channels = (ROOT / "assets/js/ui/channels.js").read_text(encoding="utf-8")
        self.assertIn('location.replace(appUrl("login.html"))', channels)
        self.assertIn('location.replace(appUrl("admin/"))', channels)
        self.assertNotIn('location.replace("/")', channels)

    def test_cloud_session_watchdog_does_not_require_local_presence_cookie(self):
        watchdog = (ROOT / "assets/js/ui/session-watchdog.js").read_text(encoding="utf-8")
        verification = (ROOT / "assets/js/ui/account-verification.js").read_text(encoding="utf-8")
        self.assertIn('const CLOUD_ORIGIN = "https://aeliteestrangeira.github.io"', watchdog)
        self.assertIn("if (location.origin === CLOUD_ORIGIN) return;", watchdog)
        self.assertIn('location.replace(appUrl("login.html"))', watchdog)
        self.assertIn('location.replace(appUrl("login.html"))', verification)
        self.assertNotIn('location.replace("/")', watchdog)
        self.assertNotIn('location.replace("/")', verification)

    def test_channels_hydrates_onboarding_assets_from_cloudinary(self):
        server_entry = (ROOT / "assets/js/ui/server-entry.js").read_text(encoding="utf-8")
        self.assertIn("const ONBOARDING_ASSET_URLS = Object.freeze({", server_entry)
        self.assertIn('querySelectorAll(\'img[src*="images/"]\')', server_entry)
        self.assertIn("hydrateOnboardingAssets(container);", server_entry)
        self.assertIn("hydrateOnboardingAssets(frame);", server_entry)
        for name in ["0209-b30f13ee315c2568", "0211-050c2ac76232eff6", "0212-261f952bf028fa34",
                     "0213-4900b53e7b34c3a5", "0214-d804200b134c9327", "0215-2f1587b0c86b42e2",
                     "0216-31f3db39524533b6", "0217-d8fed3f03866afe2"]:
            self.assertIn(f"https://res.cloudinary.com/do7vwsnpg/image/upload/", server_entry)
            self.assertIn(name, server_entry)

    def test_pages_runtime_keeps_dynamic_image_fallbacks_inside_project_root(self):
        pending = (ROOT / "assets/js/ui/friend-pending.js").read_text(encoding="utf-8")
        voice = (ROOT / "assets/js/ui/voice.js").read_text(encoding="utf-8")
        self.assertIn('appUrl("images/0208-2ccd8ae8b2379360.png")', pending)
        self.assertIn('appUrl("images/0208-2ccd8ae8b2379360.png")', voice)
        self.assertNotIn('= "/images/', pending)
        self.assertNotIn('= "/images/', voice)

    def test_cloud_admin_requires_server_allowlist_and_mfa_aal2(self):
        edge = (ROOT / "priv/supabase/functions/admin-gate/index.ts").read_text(encoding="utf-8")
        schema = (ROOT / "priv/supabase/migrations/000_current_schema.sql").read_text(encoding="utf-8")
        admin_js = (ROOT / "assets/js/admin.js").read_text(encoding="utf-8")
        self.assertIn("auth.getUser(token)", edge)
        self.assertIn("getAuthenticatorAssuranceLevel(token)", edge)
        self.assertIn('.rpc("web_admin_authorization"', edge)
        self.assertIn('aal !== "aal2"', edge)
        self.assertNotIn("decodePayload", edge)
        self.assertIn("security definer", schema)
        self.assertIn("set search_path = ''", schema)
        self.assertIn("revoke all on function public.web_admin_authorization(uuid) from authenticated", schema)
        self.assertIn("grant execute on function public.web_admin_authorization(uuid) to service_role", schema)
        self.assertNotIn("innerHTML", admin_js)
        self.assertNotIn("localStorage", admin_js)
        self.assertNotIn("sessionStorage", admin_js)


if __name__ == "__main__":
    unittest.main()
