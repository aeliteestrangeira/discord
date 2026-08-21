import { appUrl, emit } from "./runtime.js";
import { transitionState } from "./state.js";

const PRESENCE_COOKIE = "app_presence";
const SESSION_CHANNEL = "app-session-events";
const VALIDATION_DEBOUNCE_MS = 750;
const MIN_VALIDATION_GAP_MS = 5000;
const CLOUD_ORIGIN = "https://aeliteestrangeira.github.io";
let activeController = null;

function hasPresenceCookie() {
  const prefix = `${PRESENCE_COOKIE}=`;
  return document.cookie.split(";").some((part) => part.trim().startsWith(prefix));
}

export function wireSessionWatchdog(authProvider) {
  if (activeController) return activeController;

  let stopped = false;
  let inFlight = false;
  let lastValidationAt = 0;
  let debounceTimer = null;
  let channel = null;

  const cleanup = () => {
    if (debounceTimer) window.clearTimeout(debounceTimer);
    window.removeEventListener("focus", onActivity);
    window.removeEventListener("pageshow", onActivity);
    window.removeEventListener("online", onActivity);
    window.removeEventListener("storage", onStorage);
    document.removeEventListener("visibilitychange", onVisibility);
    document.removeEventListener("app:session-check", onExplicitCheck);
    try { window.cookieStore?.removeEventListener?.("change", onCookieChange); } catch (_) {}
    try { channel?.close?.(); } catch (_) {}
    channel = null;
  };

  const revoke = (code = "session_revoked") => {
    if (stopped) return;
    stopped = true;
    cleanup();
    transitionState({ status: "session-revoked" }, `session:${code}`);
    emit("app:session-revoked", { code });
    location.replace(appUrl("login.html"));
  };

  const checkPresence = () => {
    if (location.origin === CLOUD_ORIGIN) return;
    if (!stopped && !hasPresenceCookie()) revoke("session_cookie_removed");
  };

  async function check({ force = false } = {}) {
    if (stopped || inFlight) return;
    checkPresence();
    if (stopped) return;

    const now = Date.now();
    if (!force && now - lastValidationAt < MIN_VALIDATION_GAP_MS) return;
    inFlight = true;
    lastValidationAt = now;
    try {
      const result = await authProvider.validateSession();
      if (!result?.data?.authenticated) revoke(result?.error?.code || "session_revoked");
    } catch (_) {
      // Network loss is not equivalent to session revocation. Authenticated API
      // calls remain fail-closed server-side; validate again on the next browser
      // activity/online event instead of logging the user out due to connectivity.
      emit("app:session-validation-deferred", { code: "network_unavailable" });
    } finally {
      inFlight = false;
    }
  }

  const scheduleCheck = ({ force = false } = {}) => {
    checkPresence();
    if (stopped || document.visibilityState === "hidden") return;
    if (debounceTimer) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      debounceTimer = null;
      check({ force });
    }, VALIDATION_DEBOUNCE_MS);
  };

  const onActivity = () => scheduleCheck();
  const onVisibility = () => {
    checkPresence();
    if (document.visibilityState === "visible") scheduleCheck();
  };
  const onCookieChange = (event) => {
    const deleted = [...(event?.deleted || [])].some((cookie) => cookie?.name === PRESENCE_COOKIE);
    if (deleted) revoke("session_cookie_removed");
    else checkPresence();
  };
  const onExplicitCheck = () => scheduleCheck({ force: true });
  const onStorage = (event) => {
    if (event.key === "app-session-revoked" && event.newValue) revoke("session_broadcast");
  };

  // No interval polling. The authenticated HTML was already validated by the
  // server. Local logout/cookie deletion is event-driven; remote authority is
  // revalidated only on real browser activity (focus/pageshow/online) or an
  // explicit security event. This removes the former 500 ms heartbeat.
  checkPresence();
  if (!stopped) {
    window.addEventListener("focus", onActivity);
    window.addEventListener("pageshow", onActivity);
    window.addEventListener("online", onActivity);
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("app:session-check", onExplicitCheck);
    try { window.cookieStore?.addEventListener?.("change", onCookieChange); } catch (_) {}
    try {
      channel = new BroadcastChannel(SESSION_CHANNEL);
      channel.addEventListener("message", (event) => {
        if (event?.data?.type === "revoked") revoke("session_broadcast");
      });
    } catch (_) {}
  }

  activeController = Object.freeze({
    check: () => check({ force: true }),
    stop: () => { stopped = true; cleanup(); activeController = null; },
  });
  return activeController;
}
