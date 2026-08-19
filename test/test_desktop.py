from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DesktopArchitectureTests(unittest.TestCase):
    def test_desktop_files_exist(self):
        for relative in (
            "package.json", "DESKTOP_START.bat", "desktop/main.cjs", "desktop/backend.cjs",
            "desktop/security.cjs", "desktop/preload.cjs", "desktop/constants.cjs",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_renderer_is_hardened(self):
        source = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn("nodeIntegration: false", source)
        self.assertIn("contextIsolation: true", source)
        self.assertIn("sandbox: true", source)
        self.assertIn("webSecurity: true", source)
        self.assertIn("allowRunningInsecureContent: false", source)
        self.assertIn("webviewTag: false", source)
        self.assertIn("app.enableSandbox()", source)

    def test_permission_policy_is_default_deny(self):
        source = (ROOT / "desktop/security.cjs").read_text(encoding="utf-8")
        self.assertIn('if (permission !== "media") return false;', source)
        self.assertIn('details.mediaType === "audio"', source)
        self.assertIn("session.setDevicePermissionHandler(() => false)", source)
        self.assertIn('return { action: "deny" };', source)

    def test_desktop_health_route_exists(self):
        source = (ROOT / "lib/discord_app_web/controllers/pages.py").read_text(encoding="utf-8")
        self.assertIn('"/api/desktop/health"', source)
        self.assertIn('service="discord-local"', source)

    def test_public_manifest_generator_excludes_private_and_runtime_state(self):
        source = (ROOT / "priv/scripts/generate_integrity_manifest.py").read_text(encoding="utf-8")
        for value in (
            '".env"', '"config/.env"', '"config/SUPABASE_PRIVILEGED.env"',
            '"instance"', '".runtime"', '".venv"', '"node_modules"',
        ):
            self.assertIn(value, source)

    def test_restart_script_can_suppress_external_browser(self):
        source = (ROOT / "priv/scripts/restart_server.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$NoBrowser", source)
        self.assertIn("if (-not $NoBrowser)", source)

    def test_public_gitignore_keeps_secrets_and_desktop_build_state_out(self):
        source = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for value in (
            "config/SUPABASE_PRIVILEGED.env", ".env", "instance/*", ".runtime/*",
            "node_modules/", "out/",
        ):
            self.assertIn(value, source)


if __name__ == "__main__":
    unittest.main()
