import { State, transitionState } from "./state.js";
import { emit, ensureAuthProvider } from "./runtime.js";

function resolvedUsername(user) {
  const explicit = String(user?.username || "").trim().toLowerCase();
  if (explicit) return explicit;
  const email = String(user?.email || "").trim().toLowerCase();
  if (email.includes("@")) return email.split("@", 1)[0];
  return "usuário";
}

function applyProfile(user) {
  const username = resolvedUsername(user);
  for (const node of document.querySelectorAll(".title_b6c092, .hovered__0263c")) node.textContent = username;
}

function readSessionBootstrap() {
  const node = document.getElementById("app-session-bootstrap");
  if (!node) return null;
  try {
    const parsed = JSON.parse(node.textContent || "{}");
    if (parsed?.authenticated === true && parsed?.user?.id) return parsed;
  } catch (_) {}
  return null;
}

async function resolveSession(authProvider) {
  const bootstrapped = readSessionBootstrap();
  const session = bootstrapped || await authProvider.session();
  if (!session?.authenticated) {
    location.replace("/");
    return null;
  }
  if (session.role === "admin") {
    location.replace("/admin");
    return null;
  }
  return session;
}

const moduleCache = new Map();
function loadModule(name) {
  if (!moduleCache.has(name)) moduleCache.set(name, import(`./${name}.js`));
  return moduleCache.get(name);
}

async function wireImmediateShell(authProvider, session) {
  const [{ wireSessionWatchdog }, { wireGuildNavigation }] = await Promise.all([
    loadModule("session-watchdog"),
    loadModule("guild-navigation"),
  ]);
  wireSessionWatchdog(authProvider);
  wireGuildNavigation();

  if (document.querySelector(".notice__6e2b9")) {
    const { wireVerificationNotice } = await loadModule("account-verification");
    wireVerificationNotice(authProvider, session);
  }

  if (document.querySelector(".privateChannels_e6b769 .closeButton__972a0[role=\"button\"]")) {
    const { wireDirectMessageCloseButtons } = await loadModule("direct-messages");
    wireDirectMessageCloseButtons(session.user);
  }
}

async function wireRouteSpecific(authProvider) {
  const tasks = [];
  if (document.querySelector('input[name="add-friend"]')) {
    tasks.push(loadModule("friends").then(({ wireFriendRequests }) => wireFriendRequests(authProvider)));
  }
  if (document.querySelector("main.container__133bf .tabBar__133bf")) {
    tasks.push(loadModule("friend-pending").then(({ wirePendingFriendRequests }) => wirePendingFriendRequests(authProvider)));
  }
  await Promise.all(tasks);
}

function installLazyServerEntry(authProvider, user) {
  const selector = '[data-list-item-id="guildsnav___create-join-button"]';
  let ready = false;
  let loading = null;
  let replaying = false;

  const load = async () => {
    if (ready) return;
    if (!loading) {
      loading = loadModule("server-entry").then(({ wireServerEntry }) => {
        wireServerEntry(authProvider, user);
        ready = true;
      });
    }
    await loading;
  };

  const activate = async (event) => {
    if (ready || replaying) return;
    const button = event.target?.closest?.(selector);
    if (!button) return;
    if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    await load();
    replaying = true;
    try { button.click(); } finally { replaying = false; }
  };

  document.addEventListener("click", activate, true);
  document.addEventListener("keydown", activate, true);

  // A captured first-server modal is already visible UI, so its controller is
  // immediately relevant and may be loaded without waiting for another click.
  if (document.querySelector("button.closeButton_f17563.close__49fc1")) load().catch(() => {});
}

function installLazyVoice(authProvider, user) {
  const selector = 'a[aria-label*="canal de voz" i], a[data-list-item-id][aria-label*="voice channel" i]';
  let ready = false;
  let loading = null;
  let replaying = false;

  const load = async () => {
    if (!loading) {
      loading = loadModule("voice").then((module) => {
        module.rewireVoiceChannels(authProvider, user);
        ready = true;
        return module;
      });
    }
    return loading;
  };

  const activate = async (event) => {
    if (replaying) return;
    const anchor = event.target?.closest?.(selector);
    if (!anchor) return;
    if (event.type === "keydown" && event.key !== "Enter" && event.key !== " ") return;
    if (ready) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation?.();
    await load();
    replaying = true;
    try { anchor.click(); } finally { replaying = false; }
  };

  document.addEventListener("click", activate, true);
  document.addEventListener("keydown", activate, true);
  document.addEventListener("app:spa-route-applied", () => {
    if (!ready) return;
    loadModule("voice").then((module) => module.rewireVoiceChannels(authProvider, user)).catch(() => {});
  });
}

export async function wireChannelsPage() {
  if (State.page !== "channels") return;
  transitionState({ status: "loading-session" }, "channels:boot");
  try {
    const authProvider = await ensureAuthProvider();
    const session = await resolveSession(authProvider);
    if (!session) return;

    applyProfile(session.user);
    await wireImmediateShell(authProvider, session);
    installLazyServerEntry(authProvider, session.user);
    installLazyVoice(authProvider, session.user);
    await wireRouteSpecific(authProvider);

    document.addEventListener("app:spa-route-applied", () => {
      wireRouteSpecific(authProvider).catch((error) => {
        emit("app:route-feature-error", { code: error?.name || "route_feature_error" });
      });
    });

    transitionState({
      actor: session.role === "pending" ? "pending-user" : "authenticated-user",
      status: "ready",
    }, "channels:session-ready");
  } catch (error) {
    transitionState({ status: "session-error" }, "channels:session-error");
    emit("app:channels-session-error", { code: error?.name || "session_error" });
  }
}
