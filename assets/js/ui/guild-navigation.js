import { emit } from "./runtime.js";

const CACHE_TTL_MS = 60_000;
const CACHE_LIMIT = 8;
const cache = new Map();
let activeRequest = null;
let wired = false;
let appliedPath = location.pathname;

function normalizeTarget(value) {
  try {
    const url = new URL(String(value || ""), location.href);
    if (url.origin !== location.origin) return null;
    const path = url.pathname;
    if (path === "/channels/@me") return path;
    if (/^\/channels\/[0-9a-fA-F-]{36}\/[0-9a-fA-F-]{36}$/.test(path)) return path;
  } catch (_) {}
  return null;
}

function targetFromGuildNode(node) {
  const guildId = String(node?.dataset?.appGuildId || "").trim();
  const channelId = String(node?.dataset?.appGuildChannelId || "").trim();
  if (!guildId || !channelId) return null;
  return normalizeTarget(`/channels/${encodeURIComponent(guildId)}/${encodeURIComponent(channelId)}`);
}

function targetFromEvent(event) {
  const guildNode = event.target?.closest?.("[data-app-guild-id][data-app-guild-channel-id]");
  if (guildNode) return targetFromGuildNode(guildNode);
  const anchor = event.target?.closest?.('a[href^="/channels/"]');
  if (!anchor) return null;
  return normalizeTarget(anchor.getAttribute("href"));
}

function cacheSet(path, html) {
  if (path === "/channels/@me") return;
  cache.delete(path);
  cache.set(path, { html, at: Date.now() });
  while (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
}

function cacheGet(path) {
  if (path === "/channels/@me") return null;
  const entry = cache.get(path);
  if (!entry) return null;
  if (Date.now() - entry.at > CACHE_TTL_MS) {
    cache.delete(path);
    return null;
  }
  return entry.html;
}

function setBusy(busy) {
  const page = document.querySelector(".page__5e434");
  if (!page) return;
  if (busy) page.setAttribute("aria-busy", "true");
  else page.removeAttribute("aria-busy");
}

function importReplacement(targetDocument, selector) {
  const current = document.querySelector(selector);
  const next = targetDocument.querySelector(selector);
  if (!current || !next) return false;
  current.replaceWith(document.importNode(next, true));
  return true;
}

function syncJsonBootstrap(targetDocument, id) {
  const next = targetDocument.getElementById(id);
  const current = document.getElementById(id);
  if (!next) {
    current?.remove();
    return null;
  }
  let data = null;
  try { data = JSON.parse(next.textContent || "{}"); } catch (_) {}
  if (current) current.textContent = next.textContent || "{}";
  else document.body.appendChild(document.importNode(next, true));
  return data;
}

function updateBootstraps(targetDocument) {
  const guild = syncJsonBootstrap(targetDocument, "app-guild-bootstrap");
  syncJsonBootstrap(targetDocument, "app-friend-pending-bootstrap");
  return guild;
}

function applyTreeSelection(treeItem, selected) {
  if (!treeItem) return;
  treeItem.classList.toggle("selected__6e9f8", selected);
  treeItem.setAttribute("aria-selected", selected ? "true" : "false");
  treeItem.closest(".listItemWrapper__91816")?.classList.toggle("selected__91816", selected);
  const item = treeItem.closest(".listItem__650eb");
  item?.querySelector(".item__58105")?.classList.toggle("visible__58105", selected);
  item?.querySelector(".item__58105")?.classList.toggle("selected__58105", selected);
  item?.querySelector(".blobContainer_e5445c")?.classList.toggle("selected_e5445c", selected);
}

function updatePersistentGuildRail(path, guild) {
  const home = document.querySelector('[data-list-item-id="guildsnav___home"]');
  applyTreeSelection(home, path === "/channels/@me");
  const activeGuildId = path === "/channels/@me" ? "" : String(guild?.id || path.split("/")[2] || "");
  for (const node of document.querySelectorAll("[data-app-guild-id]")) {
    const treeItem = node.querySelector('[data-list-item-id^="guildsnav___"]');
    applyTreeSelection(treeItem, String(node.dataset.appGuildId || "") === activeGuildId);
  }
}

function applyDocument(path, html, { push = true } = {}) {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  if (!parsed.querySelector(".sidebarList__5e434") || !parsed.querySelector(".page__5e434")) {
    throw new Error("spa_fragment_invalid");
  }

  // Persistent SPA shell: the guild rail and account panel are deliberately
  // untouched. Only route-scoped navigation/content and the compact title are
  // replaced. This prevents guild/avatar/username chrome from repainting.
  importReplacement(parsed, ".sidebarList__5e434");
  importReplacement(parsed, ".page__5e434");
  importReplacement(parsed, ".title_c38106");
  const guild = updateBootstraps(parsed);
  updatePersistentGuildRail(path, guild);
  document.title = parsed.title || document.title;
  if (push && location.pathname !== path) history.pushState({ appSpa: true }, "", path);
  appliedPath = path;
  emit("app:spa-route-applied", { path, guildId: String(guild?.id || ""), channelId: String(guild?.channelId || "") });
}

async function load(path, { push = true } = {}) {
  const target = normalizeTarget(path);
  if (!target || target === appliedPath) return;

  const cached = cacheGet(target);
  if (cached) {
    applyDocument(target, cached, { push });
    return;
  }

  activeRequest?.abort?.();
  const controller = new AbortController();
  activeRequest = controller;
  setBusy(true);
  const started = performance.now();
  try {
    const response = await fetch(target, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      redirect: "follow",
      signal: controller.signal,
      headers: {
        "Accept": "text/html",
        "X-App-SPA": "1",
      },
    });
    if (!response.ok || !response.url.startsWith(location.origin + "/channels/")) {
      location.assign(response.url || target);
      return;
    }
    const html = await response.text();
    cacheSet(target, html);
    applyDocument(target, html, { push });
    emit("app:guild-navigation-complete", { path: target, durationMs: Math.round(performance.now() - started) });
  } catch (error) {
    if (error?.name === "AbortError") return;
    emit("app:guild-navigation-error", { path: target, code: error?.name || "navigation_error" });
    location.assign(target);
  } finally {
    if (activeRequest === controller) activeRequest = null;
    setBusy(false);
  }
}

export function clearGuildNavigationCache() {
  cache.clear();
}

export function wireGuildNavigation() {
  if (wired) return Object.freeze({ navigate: load, clearCache: clearGuildNavigationCache });
  wired = true;

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = targetFromEvent(event);
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    emit("app:guild-navigation", { path: target });
    load(target);
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = targetFromEvent(event);
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    load(target);
  }, true);

  window.addEventListener("popstate", () => {
    const target = normalizeTarget(location.pathname);
    if (target) load(target, { push: false });
  });

  document.addEventListener("app:guild-created", clearGuildNavigationCache);
  return Object.freeze({ navigate: load, clearCache: clearGuildNavigationCache });
}
