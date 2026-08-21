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
BUILDER = ROOT / "priv" / "scripts" / "build_pages.py"


class PagesPublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory(prefix="discord-pages-test-")
        cls.output = Path(cls._temporary.name) / "site"
        subprocess.run(
            [sys.executable, str(BUILDER), "--output", str(cls.output)],
            cwd=ROOT,
            check=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_direct_application_is_published_without_landing_page(self):
        index = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("Boas-vindas de volta!", index)
        self.assertIn('href="discord.css"', index)
        self.assertRegex(index, r'src="runtime/[a-f0-9]{16}/ui\.js"')
        self.assertNotIn("WINDOWS DESKTOP", index)
        for relative in [
            "login.html",
            "register.html",
            "channels.html",
            "guild.html",
            "admin/index.html",
        ]:
            self.assertTrue((self.output / relative).is_file(), relative)

    def test_project_pages_paths_are_generated_without_mutating_sources(self):
        channels_source = (ROOT / "priv/static/pages/channels.html").read_text(encoding="utf-8")
        channels = (self.output / "channels.html").read_text(encoding="utf-8")
        guild = (self.output / "guild.html").read_text(encoding="utf-8")
        self.assertNotIn('src="runtime/', channels_source)
        self.assertRegex(channels, r'<script src="runtime/[a-f0-9]{16}/ui\.js" defer></script>')
        self.assertIn('href="channels.css"', channels)
        self.assertNotIn('href="/channels.css"', channels)
        self.assertIn('href="guild.css"', guild)
        self.assertNotIn('href="/guild.css"', guild)
        self.assertNotIn('src="/images/', channels)

    def test_every_canonical_image_reference_has_a_pages_fallback(self):
        channels = (self.output / "channels.html").read_text(encoding="utf-8")
        channels_css = (self.output / "channels.css").read_text(encoding="utf-8")
        referenced = set(re.findall(r'images/([^"\')]+)', channels))
        referenced.update(re.findall(r'images/([^"\')]+)', channels_css))
        self.assertEqual(len(referenced), 150)
        missing = sorted(name for name in referenced if not (self.output / "images" / name).is_file())
        self.assertEqual(missing, [])

    def test_runtime_and_cloud_controls_are_in_the_artifact(self):
        runtime_dirs = [path for path in (self.output / "runtime").iterdir() if path.is_dir()]
        self.assertEqual(len(runtime_dirs), 1)
        runtime = runtime_dirs[0]
        for relative in ["ui.js", "ui/state.js", "captcha.css"]:
            self.assertTrue((runtime / relative).is_file(), relative)
        for relative in ["auth-provider.js", "cloud-runtime.js", "admin.js", "admin-web.css"]:
            self.assertTrue((self.output / relative).is_file(), relative)

        cloud_runtime = (self.output / "cloud-runtime.js").read_text(encoding="utf-8")
        self.assertIn("aeliteestrangeira.github.io", cloud_runtime)
        self.assertIn("@supabase/supabase-js@2.112.3", cloud_runtime)
        self.assertIn("exchangeCodeForSession(authCode)", cloud_runtime)
        self.assertNotIn("sb_secret_", cloud_runtime)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", cloud_runtime)

    def test_onboarding_assets_are_hydrated_from_cloudinary(self):
        server_entry = (ROOT / "assets/js/ui/server-entry.js").read_text(encoding="utf-8")
        self.assertIn('querySelectorAll(\'img[src*="images/"]\')', server_entry)
        for stem in [
            "0209-b30f13ee315c2568",
            "0211-050c2ac76232eff6",
            "0212-261f952bf028fa34",
            "0213-4900b53e7b34c3a5",
            "0214-d804200b134c9327",
            "0215-2f1587b0c86b42e2",
            "0216-31f3db39524533b6",
            "0217-d8fed3f03866afe2",
        ]:
            self.assertIn(stem, server_entry)
        self.assertGreaterEqual(server_entry.count("https://res.cloudinary.com/do7vwsnpg/"), 8)

    def test_integrity_evidence_matches_built_files(self):
        info = json.loads((self.output / "BUILD_INFO.json").read_text(encoding="utf-8"))
        self.assertEqual(info["artifact"], "github-pages-direct-app")
        for name, digest in info["frozenSourceSha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)

        manifest = (self.output / "PAGES_SHA256.txt").read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(manifest), 200)
        for line in manifest:
            digest, name = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.output / name).read_bytes()).hexdigest(), digest, name)

    def test_supabase_sources_cover_every_deployed_function(self):
        expected = {"public-config", "username-availability", "admin-gate"}
        functions = {
            path.name
            for path in (ROOT / "supabase/functions").iterdir()
            if path.is_dir() and (path / "index.ts").is_file()
        }
        self.assertEqual(functions, expected)

        config = (ROOT / "supabase/config.toml").read_text(encoding="utf-8")
        self.assertIn('[functions.public-config]', config)
        self.assertIn('[functions.username-availability]', config)
        self.assertIn('[functions.admin-gate]', config)
        self.assertRegex(config, r'\[functions\.admin-gate\]\s+verify_jwt = true')

        schema = (ROOT / "supabase/migrations/000_current_schema.sql").read_text(encoding="utf-8")
        self.assertIn("enable row level security", schema.lower())
        self.assertIn("web_admin_authorization", schema)
        self.assertIn("set search_path = ''", schema)

    def test_legacy_local_runtime_cannot_return_to_the_repository(self):
        forbidden = [
            ".github/workflows/release-desktop.yml",
            "app.py",
            "config",
            "desktop",
            "lib",
            "package.json",
            "requirements.txt",
            "SERVER.bat",
            "priv/architecture",
            "assets/cloudinary-source",
        ]
        tracked = set(subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True
        ).splitlines())
        present = [
            relative
            for relative in forbidden
            if relative in tracked or any(path.startswith(f"{relative}/") for path in tracked)
        ]
        self.assertEqual(present, [])

    def test_workflows_match_the_current_web_scope(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover", ci)
        self.assertIn("node --check", ci)
        self.assertNotIn("electron", ci.lower())
        self.assertIn('"assets/pages-images/**"', pages)
        self.assertIn("python priv/scripts/build_pages.py --output _site", pages)


if __name__ == "__main__":
    unittest.main()
