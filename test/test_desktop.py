from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DesktopArchitectureTests(unittest.TestCase):
    def test_desktop_files_exist(self):
        for relative in (
            "package.json", "DESKTOP_START.bat", "MIGRATE_ALPHA_DATA.bat", "MIGRATE_ALPHA_DATA.ps1",
            "desktop/main.cjs", "desktop/backend.cjs", "desktop/security.cjs",
            "desktop/preload.cjs", "desktop/constants.cjs", "desktop/updater.cjs",
            "desktop/packaged_setup.ps1", "desktop/build_backend.ps1",
            ".github/workflows/pages.yml", ".github/workflows/release-desktop.yml",
            "priv/scripts/build_pages.py", "test/test_pages_publish.py",
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

    def test_public_manifest_generator_excludes_private_and_build_state(self):
        source = (ROOT / "priv/scripts/generate_integrity_manifest.py").read_text(encoding="utf-8")
        for value in (
            '".env"', '"config/.env"', '"config/SUPABASE_PRIVILEGED.env"',
            '"priv/supabase/config.toml"', '"priv/supabase/.gitignore"',
            '"instance"', '".runtime"', '".temp"', '".venv"', '"node_modules"', '"out"', '"build"',
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
            "node_modules/", "out/", "build/",
        ):
            self.assertIn(value, source)

    def test_packaged_state_is_outside_install_directory(self):
        paths = (ROOT / "lib/discord_app/paths.py").read_text(encoding="utf-8")
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn('"DISCORD_INSTANCE_DIR"', paths)
        self.assertIn('"DISCORD_RUNTIME_DIR"', paths)
        self.assertIn('"DISCORD_PRIVATE_ENV_FILE"', paths)
        self.assertIn('"AEliteEstrangeira", "DiscordDesktop"', main)
        self.assertIn("DISCORD_PRIVATE_CONFIG_DIR", backend)

    def test_updater_has_no_periodic_polling_loop(self):
        source = (ROOT / "desktop/updater.cjs").read_text(encoding="utf-8")
        self.assertIn("MIN_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000", source)
        self.assertIn("autoUpdater.autoDownload = false", source)
        self.assertNotIn("setInterval(", source)
        self.assertIn("autoUpdater.checkForUpdates()", source)

    def test_release_uses_nsis_and_github_provider(self):
        source = (ROOT / "package.json").read_text(encoding="utf-8")
        self.assertIn('"target": "nsis"', source)
        self.assertIn('"provider": "github"', source)
        self.assertIn('"electron-updater": "6.8.9"', source)
        self.assertIn('"electron-builder": "26.15.3"', source)

    def test_pages_publish_is_generated_from_canonical_app(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        builder = (ROOT / "priv/scripts/build_pages.py").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "site/index.html").exists())
        self.assertIn("python priv/scripts/build_pages.py --output _site", workflow)
        self.assertIn("path: _site", workflow)
        self.assertIn('"index.html": "login.html"', builder)
        self.assertIn('STATIC_PAGES = ROOT / "priv" / "static" / "pages"', builder)

    def test_pyinstaller_data_sources_are_absolute_before_spec_generation(self):
        source = (ROOT / "desktop/build_backend.ps1").read_text(encoding="utf-8")
        self.assertIn("function Data-Argument", source)
        self.assertIn("[System.IO.Path]::GetFullPath", source)
        self.assertIn('(Data-Argument "assets" "assets")', source)
        self.assertNotIn('"--add-data", "assets;assets"', source)


    def test_packaged_runtime_uses_trusted_absolute_windows_tool_paths(self):
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        hostname = (ROOT / "priv/scripts/ensure_local_hostname.ps1").read_text(encoding="utf-8")
        setup = (ROOT / "desktop/packaged_setup.ps1").read_text(encoding="utf-8")
        self.assertIn("function resolveWindowsPowerShell", backend)
        self.assertIn('"WindowsPowerShell", "v1.0", "powershell.exe"', backend)
        self.assertIn("function resolveSystem32Executable", backend)
        self.assertNotIn('run(\n    "powershell.exe"', backend)
        self.assertIn("Get-CurrentPowerShellExecutable", hostname)
        self.assertIn("Get-Process -Id $PID", hostname)
        self.assertNotIn('Start-Process -FilePath "powershell.exe"', hostname)
        self.assertIn('System32\\icacls.exe', setup)


    def test_packaged_powershell_uses_persistent_real_working_directory(self):
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn('cwd = process.cwd()', backend)
        self.assertIn('cwd-error', backend)
        self.assertIn('"hostname", { env, cwd: dataRoot }', backend)
        self.assertIn('"desktop-data-acl-and-trust", { env, cwd: dataRoot }', backend)
        self.assertIn('phase: "python-dependencies",\n    cwd: SOURCE_ROOT', backend)
        self.assertNotIn('cwd = SOURCE_ROOT', backend)

    def test_integrity_hashes_are_eol_canonical(self):
        generator = (ROOT / "priv/scripts/generate_integrity_manifest.py").read_text(encoding="utf-8")
        verifier = (ROOT / "verify_integrity.py").read_text(encoding="utf-8")
        for source in (generator, verifier):
            self.assertIn("canonical_bytes", source)
            self.assertIn('CRLF_TEXT_SUFFIXES = {".bat"}', source)
            self.assertIn('".svg", ".example"', source)
            self.assertIn('LF_TEXT_NAMES = {".gitattributes", ".gitignore"}', source)


if __name__ == "__main__":
    unittest.main()
