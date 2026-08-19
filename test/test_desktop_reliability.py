from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DesktopReliabilityTests(unittest.TestCase):
    def test_hcaptcha_is_prewarmed_and_uses_sdk_readiness_callback(self):
        captcha = (ROOT / "assets/js/ui/captcha.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "assets/js/ui/bootstrap.js").read_text(encoding="utf-8")
        self.assertIn('const HCAPTCHA_ONLOAD_CALLBACK = "__discordHCaptchaReady";', captcha)
        self.assertIn("onload=${encodeURIComponent(HCAPTCHA_ONLOAD_CALLBACK)}", captcha)
        self.assertIn("async function prewarmCaptcha()", captcha)
        self.assertIn("await Promise.all([ensureCaptchaCss(), ensureHCaptchaApi()])", captcha)
        self.assertNotIn('script.addEventListener("load", () => resolve(window.hcaptcha)', captcha)
        self.assertGreaterEqual(bootstrap.count("prewarmHumanVerification();"), 2)

    def test_hcaptcha_rebuilds_widget_once_and_logs_sanitized_provider_state(self):
        captcha = (ROOT / "assets/js/ui/captcha.js").read_text(encoding="utf-8")
        self.assertIn("providerRetryUsed", captcha)
        self.assertIn('new Set(["rate-limited", "invalid-data", "script-error"])', captcha)
        self.assertIn("api.remove(currentId)", captcha)
        self.assertIn("mount.replaceChildren()", captcha)
        self.assertIn("renderWidget({ continueFlow: true })", captcha)
        self.assertIn("api.execute(currentId, { async: true })", captcha)
        self.assertIn("[hcaptcha] provider-error code=", captcha)
        self.assertIn("const canRecover = !providerRetryUsed", captcha)
        self.assertNotIn("transientRetryUsed", captcha)

    def test_hcaptcha_renderer_diagnostics_are_filtered_into_desktop_log(self):
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn('win.webContents.on("console-message"', main)
        self.assertIn('message.startsWith("[hcaptcha]")', main)
        self.assertIn('log(`renderer ${message.slice(0, 300)}`)', main)
        self.assertNotIn('log(`renderer-console ${details?.message}`)', main)

    def test_home_icon_routes_to_direct_messages_and_dm_group_is_route_scoped(self):
        nav = (ROOT / "assets/js/ui/guild-navigation.js").read_text(encoding="utf-8")
        self.assertIn('guildsnav___home', nav)
        self.assertIn('if (home) return "/channels/@me";', nav)
        self.assertIn('document.getElementById("guild-list-unread-dms")', nav)
        self.assertIn("syncPersistentDmGroup(parsed, path);", nav)
        self.assertIn("unreadDmGroup.hidden = !onDirectMessages;", nav)
        self.assertIn('replacement.hidden = !onDirectMessages;', nav)

    def test_core_css_and_js_do_not_depend_on_conditional_cache(self):
        assets = (ROOT / "lib/discord_app_web/controllers/assets.py").read_text(encoding="utf-8")
        security = (ROOT / "lib/discord_app_web/security.py").read_text(encoding="utf-8")
        self.assertIn("conditional=False, max_age=0", assets)
        self.assertIn('"Cache-Control"] = "no-store, max-age=0"', assets)
        self.assertIn("_no_store_static(ASSET_CSS_DIR, filename)", assets)
        self.assertIn("_no_store_static(ASSET_JS_DIR, filename)", assets)
        self.assertIn("_no_store_static(UI_JS_DIR, filename)", assets)
        self.assertIn('(".html", ".js", ".css")', security)

    def test_every_packaged_startup_checks_for_n_plus_one(self):
        updater = (ROOT / "desktop/updater.cjs").read_text(encoding="utf-8")
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn("manual = false, startup = false", updater)
        self.assertIn("!manual && !startup && !checkDue()", updater)
        self.assertIn('log("[updater] startup-check")', updater)
        self.assertIn("checkForUpdates({ manual: false, startup: true })", main)
        function = updater.split("async function checkForUpdates", 1)[1]
        before_remote, after_remote = function.split("await autoUpdater.checkForUpdates()", 1)
        self.assertNotIn("markChecked();", before_remote)
        self.assertIn("markChecked();", after_remote)

    def test_desktop_release_version_is_4_3_3(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "4.3.3")


if __name__ == "__main__":
    unittest.main()
