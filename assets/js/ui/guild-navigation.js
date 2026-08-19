import { emit } from "./runtime.js";

let wired = false;

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
  const home = event.target?.closest?.('[data-list-item-id="guildsnav___home"]');
  if (home) return "/channels/@me";
  const guildNode = event.target?.closest?.("[data-app-guild-id][data-app-guild-channel-id]");
  if (guildNode) return targetFromGuildNode(guildNode);
  const anchor = event.target?.closest?.('a[href^="/channels/"]');
  if (!anchor) return null;
  return normalizeTarget(anchor.getAttribute("href"));
}

async function navigate(path) {
  const target = normalizeTarget(path);
  if (!target || target === location.pathname) return false;
  emit("app:guild-navigation", { path: target, mode: "document" });
  // Reliability boundary for 4.3.4: guild/home transitions use a complete
  // document navigation. This guarantees that toolbar, member list, route
  // controllers and captured DOM are hydrated from the same server response.
  location.assign(target);
  return true;
}

export function clearGuildNavigationCache() {
  // Partial-document caching is intentionally disabled until every persistent
  // shell component has an explicit mount/unmount/rehydrate lifecycle.
}

export function wireGuildNavigation() {
  if (wired) return Object.freeze({ navigate, clearCache: clearGuildNavigationCache });
  wired = true;

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = targetFromEvent(event);
    if (!target || target === location.pathname) return;
    event.preventDefault();
    event.stopPropagation();
    void navigate(target);
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = targetFromEvent(event);
    if (!target || target === location.pathname) return;
    event.preventDefault();
    event.stopPropagation();
    void navigate(target);
  }, true);

  return Object.freeze({ navigate, clearCache: clearGuildNavigationCache });
}
