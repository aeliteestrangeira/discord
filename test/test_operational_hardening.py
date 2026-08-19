from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OperationalHardeningTests(unittest.TestCase):
    def test_production_wsgi_server_replaces_flask_development_server(self):
        app = (ROOT / "lib/discord_app_web/app.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("hypercorn>=0.18,<0.19", requirements)
        self.assertIn("from hypercorn.asyncio import serve", app)
        self.assertIn('mode="wsgi"', app)
        self.assertIn("config.certfile", app)
        self.assertIn("config.keyfile", app)
        self.assertIn("config.include_server_header = False", app)
        self.assertNotIn("app.run(", app)

    def test_health_is_bound_to_the_spawned_backend_instance(self):
        pages = (ROOT / "lib/discord_app_web/controllers/pages.py").read_text(encoding="utf-8")
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn("DESKTOP_INSTANCE_MARKER", pages)
        self.assertIn("expectedHealthMarker = marker", backend)
        self.assertIn("body.marker !== expectedHealthMarker", backend)
        self.assertIn("instancia antiga do backend", backend)

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

    def test_release_pipeline_smokes_packaged_wsgi_backend(self):
        workflow = (ROOT / ".github/workflows/release-desktop.yml").read_text(encoding="utf-8")
        self.assertIn("Smoke test packaged WSGI backend", workflow)
        self.assertIn("ci-smoke", workflow)
        self.assertIn("Packaged Hypercorn WSGI/TLS health check passed.", workflow)


if __name__ == "__main__":
    unittest.main()
