from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OperationalHardeningTests(unittest.TestCase):
    def test_native_wsgi_server_replaces_async_wsgi_bridge(self):
        app = (ROOT / "lib/discord_app_web/app.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("cheroot>=11.1.2,<12", requirements)
        self.assertNotIn("hypercorn", requirements.lower())
        self.assertIn("from cheroot import wsgi", app)
        self.assertIn("BuiltinSSLAdapter", app)
        self.assertIn("server.start()", app)
        self.assertNotIn("asyncio.run", app)
        self.assertNotIn("app.run(", app)

    def test_health_is_bound_to_the_spawned_backend_instance(self):
        pages = (ROOT / "lib/discord_app_web/controllers/pages.py").read_text(encoding="utf-8")
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn("DESKTOP_INSTANCE_MARKER", pages)
        self.assertIn("expectedHealthMarker = marker", backend)
        self.assertIn("body.marker !== expectedHealthMarker", backend)
        self.assertIn("marker divergente", backend)
        self.assertIn("payload inesperado", backend)

    def test_stale_backend_recovery_is_path_scoped_and_fail_closed(self):
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn("reclaimBackendPort", backend)
        self.assertIn("executablePathForPid", backend)
        self.assertIn("Get-CimInstance Win32_Process", backend)
        self.assertIn("processo nao confiavel", backend)
        self.assertIn('"taskkill.exe"', backend)
        self.assertIn('"/PID", String(pid), "/T", "/F"', backend)
        self.assertIn("legacyBackendExe", backend)

    def test_long_running_backend_is_onedir_not_onefile(self):
        build = (ROOT / "desktop/build_backend.ps1").read_text(encoding="utf-8")
        package = (ROOT / "package.json").read_text(encoding="utf-8")
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn('"--noconfirm", "--clean", "--onedir"', build)
        self.assertIn('"--noconfirm", "--clean", "--onefile"', build)
        self.assertIn('discord-backend\\discord-backend.exe', build)
        self.assertIn('"filter": [\n          "**/*"\n        ]', package)
        self.assertIn('"discord-backend", "discord-backend.exe"', backend)

    def test_packaged_backend_stop_waits_and_can_force_process_tree(self):
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn("terminateTrackedBackend", backend)
        self.assertIn("waitForChildExit(child, 3000)", backend)
        self.assertIn("backend-force-stop", backend)
        self.assertIn("expectedHealthMarker = null", backend)

    def test_packaged_python_and_node_logs_are_utf8_safe(self):
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn('PYTHONUTF8: "1"', backend)
        self.assertIn('PYTHONIOENCODING: "utf-8"', backend)
        self.assertIn('StringDecoder("utf8")', backend)
        self.assertIn("logUtf8Lines", backend)

    def test_passkey_capability_is_checked_before_experimental_options_endpoint(self):
        source = (ROOT / "lib/discord_app_web/controllers/auth/passkey.py").read_text(encoding="utf-8")
        settings_pos = source.index("provider.public_auth_settings()")
        options_pos = source.index("provider.start_passkey_authentication()")
        self.assertLess(settings_pos, options_pos)
        self.assertIn('settings.get("passkeys_enabled") is not True', source)
        self.assertIn('"passkey_disabled"', source)
        self.assertIn('"passkey_capability_unavailable"', source)

    def test_updater_progress_logging_is_bucketed_and_err_aborted_is_suppressed(self):
        updater = (ROOT / "desktop/updater.cjs").read_text(encoding="utf-8")
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn("Math.floor(raw / 5) * 5", updater)
        self.assertIn("bucket <= lastProgressBucket", updater)
        self.assertIn("errorCode === -3", main)

    def test_release_pipeline_smokes_restart_on_same_port(self):
        workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(encoding="utf-8")
        self.assertIn("Smoke test packaged WSGI backend restart", workflow)
        self.assertIn("ci-smoke-1", workflow)
        self.assertIn("ci-smoke-2", workflow)
        self.assertIn("Packaged Cheroot WSGI/TLS restart health check passed.", workflow)
        self.assertIn("discord-backend/discord-backend.exe", workflow.replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
