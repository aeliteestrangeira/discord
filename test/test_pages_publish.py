from __future__ import annotations

import hashlib
import json
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
            self.assertIn('src="ui.js"', index)
            self.assertNotIn("O mesmo site, agora em aplicativo desktop.", index)
            self.assertNotIn("WINDOWS DESKTOP", index)
            self.assertTrue((output / "register.html").is_file())
            self.assertTrue((output / "channels.html").is_file())
            self.assertTrue((output / "guild.html").is_file())
            self.assertTrue((output / "admin/index.html").is_file())
            self.assertTrue((output / "ui/bootstrap.js").is_file())
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
        self.assertIn('const APP_ROOT_URL = new URL("../", import.meta.url);', runtime)
        self.assertIn('script.src = new URL("auth-provider.js", APP_ROOT_URL).href;', runtime)
        self.assertIn("location.assign(appUrl(target));", runtime)
        self.assertIn('const appRootPath = new URL("../", import.meta.url).pathname.toLowerCase();', state)
        self.assertIn('link.href = new URL("../captcha.css", import.meta.url).href;', captcha)

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
