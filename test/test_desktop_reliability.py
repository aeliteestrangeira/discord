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
        self.assertIn("await ensureHCaptchaApi();", captcha)
        self.assertIn('const sdkHost = String(location.hostname || "").trim().toLowerCase();', captcha)
        self.assertIn("&host=${encodeURIComponent(sdkHost)}", captcha)
        self.assertIn("[hcaptcha] sdk-load host=${sdkHost}", captcha)
        self.assertNotIn('script.addEventListener("load", () => resolve(window.hcaptcha)', captcha)
        self.assertGreaterEqual(bootstrap.count("prewarmHumanVerification();"), 2)

    def test_hcaptcha_uses_visible_modal_and_closes_after_success_or_cancel(self):
        captcha = (ROOT / "assets/js/ui/captcha.js").read_text(encoding="utf-8")
        self.assertIn("Promise.all([ensureCaptchaCss(), ensureHCaptchaApi()])", captcha)
        self.assertIn("replaceTrustedChildren(layer, captchaModalMarkup())", captcha)
        self.assertIn('OverlayManager.claim({ id: "hcaptcha", type: "modal", close: cancel })', captcha)
        self.assertIn('close?.addEventListener("click", cancel, { once: true })', captcha)
        self.assertIn('document.addEventListener("keydown", onKeyDown, true)', captcha)
        self.assertIn('OverlayManager.release("hcaptcha")', captcha)
        self.assertIn('console.info("[hcaptcha] visible-success")', captcha)
        self.assertIn('mode=visible', captcha)
        self.assertNotIn('size: "invisible"', captcha)
        self.assertNotIn("api.execute(widgetId", captcha)
        success = captcha.split('callback: (value) => {', 1)[1].split('"expired-callback"', 1)[0]
        self.assertLess(success.index("cleanup();"), success.index("resolve(token);"))

    def test_hcaptcha_renderer_diagnostics_are_filtered_into_desktop_log(self):
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn('win.webContents.on("console-message"', main)
        self.assertIn('message.startsWith("[hcaptcha]")', main)
        self.assertIn('log(`renderer ${message.slice(0, 300)}`)', main)
        self.assertNotIn('log(`renderer-console ${details?.message}`)', main)

    def test_packaged_log_root_is_initialized_before_hcaptcha_diagnostics(self):
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        backend = (ROOT / "desktop/backend.cjs").read_text(encoding="utf-8")
        self.assertIn("function initializeDesktopLog(dataRoot)", backend)
        self.assertIn("initializeDesktopLog,", backend)
        self.assertIn("initializeDesktopLog(dataRoot);", main)
        self.assertIn("desktop process start mode=", main)
        early = main.split("const gotLock", 1)[0]
        self.assertIn("initializeDesktopLog(dataRoot);", early)
        start = main.split("async function startDesktop()", 1)[1]
        self.assertLess(start.index("try {"), start.index("installHCaptchaNetworkDiagnostics(desktopSession);"))
        self.assertIn("try { log(`ready-failure:", main)
        self.assertIn("app.quit();", main)

    def test_hcaptcha_network_diagnostics_are_queryless_and_fail_closed(self):
        main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
        self.assertIn("HCAPTCHA_NETWORK_FILTER", main)
        self.assertIn("webRequest.onErrorOccurred", main)
        self.assertIn("webRequest.onCompleted", main)
        self.assertIn("[hcaptcha-net] diagnostics-installed", main)
        self.assertIn("[hcaptcha-net] error target=", main)
        self.assertIn("[hcaptcha-net] http target=", main)
        self.assertIn("parsed.pathname", main)
        self.assertIn("installHCaptchaNetworkDiagnostics(desktopSession)", main)
        self.assertIn("certificate-error target=${safeNetworkTarget(url)}", main)
        self.assertNotIn("certificate-error url=${url}", main)
        diagnostics = main.split("function safeNetworkTarget", 1)[1].split("function createWindow", 1)[0]
        self.assertNotIn(".search", diagnostics)
        self.assertNotIn(".searchParams", diagnostics)
        self.assertNotIn("details.requestHeaders", diagnostics)
        self.assertNotIn("details.uploadData", diagnostics)
        self.assertNotIn("details.url}", diagnostics)
        self.assertIn("callback(false);", main)

    def test_guild_navigation_uses_full_document_reload_until_shell_lifecycle_is_complete(self):
        nav = (ROOT / "assets/js/ui/guild-navigation.js").read_text(encoding="utf-8")
        self.assertIn('guildsnav___home', nav)
        self.assertIn('if (home) return "/channels/@me";', nav)
        self.assertIn("location.assign(target);", nav)
        self.assertIn('mode: "document"', nav)
        self.assertNotIn("new DOMParser()", nav)
        self.assertNotIn("fetch(target", nav)
        self.assertNotIn("history.pushState", nav)
        self.assertNotIn("CACHE_TTL_MS", nav)

    def test_public_repository_has_no_admin_provisioner(self):
        self.assertFalse((ROOT / "INSTALL_ADMIN.bat").exists())
        self.assertFalse((ROOT / "priv/scripts/install_admin.py").exists())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("`INSTALL_ADMIN.bat`", readme)
        self.assertIn("ferramenta privada externa", readme)

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

    def test_desktop_release_version_is_4_3_8(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["version"], "4.3.8")


if __name__ == "__main__":
    unittest.main()
