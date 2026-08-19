import { emit } from "./runtime.js";

const CLOSED_DM_STORAGE_KEY = "app.closed-direct-messages.v1";

function storageKeyForUser(user) {
  const identity = String(user?.id || user?.username || user?.email || "anonymous").trim().toLowerCase();
  return `${CLOSED_DM_STORAGE_KEY}:${identity || "anonymous"}`;
}

function readClosedConversationIds(storageKey) {
  try {
    const parsed = JSON.parse(localStorage.getItem(storageKey) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.filter((value) => typeof value === "string" && value) : []);
  } catch (_) {
    return new Set();
  }
}

function writeClosedConversationIds(storageKey, ids) {
  try {
    localStorage.setItem(storageKey, JSON.stringify([...ids]));
  } catch (_) {
    // Persistence is best-effort; both visual projections are still removed.
  }
}

function conversationIdForRow(row) {
  const link = row?.querySelector('a.link__972a0[data-list-item-id]');
  const listId = String(link?.dataset.listItemId || "").trim();
  if (listId) return listId;
  const href = String(link?.getAttribute("href") || "").trim();
  return href || "";
}

function conversationEntityId(conversationId) {
  const value = String(conversationId || "").trim();
  const marker = value.lastIndexOf("___");
  if (marker >= 0) return value.slice(marker + 3);
  const hrefMatch = value.match(/\/channels\/@me\/([^/?#]+)/);
  return hrefMatch ? decodeURIComponent(hrefMatch[1]) : value;
}

function directMessageRows() {
  return document.querySelectorAll('.privateChannels_e6b769 li.dm__972a0.channel__972a0');
}

function unreadDmTile(entityId) {
  const group = document.getElementById("guild-list-unread-dms");
  if (!group || !entityId) return null;
  const candidates = group.querySelectorAll('[data-list-item-id^="guildsnav___"]');
  const targetId = `guildsnav___${entityId}`;
  const item = [...candidates].find((node) => String(node.dataset.listItemId || "") === targetId);
  if (!item) return null;
  let tile = item;
  while (tile && tile.parentElement !== group) tile = tile.parentElement;
  return tile?.parentElement === group ? tile : null;
}

function removeConversationProjections(conversationId, row = null) {
  if (row?.isConnected) row.remove();
  const entityId = conversationEntityId(conversationId);
  unreadDmTile(entityId)?.remove();
}

function removeClosedRows(closedIds) {
  for (const row of directMessageRows()) {
    const id = conversationIdForRow(row);
    if (id && closedIds.has(id)) removeConversationProjections(id, row);
  }
}

function closeDirectMessage(button, storageKey, closedIds) {
  const row = button?.closest('li.dm__972a0.channel__972a0');
  if (!row) return;
  const id = conversationIdForRow(row);
  if (id) {
    closedIds.add(id);
    writeClosedConversationIds(storageKey, closedIds);
  }
  const scroller = row.closest('.scroller__99e7c');
  removeConversationProjections(id, row);
  if (scroller?.isConnected && typeof scroller.focus === "function") {
    scroller.focus({ preventScroll: true });
  }
  emit("app:direct-message-closed", { conversationId: id || null, entityId: conversationEntityId(id) || null });
}

export function wireDirectMessageCloseButtons(user) {
  const storageKey = storageKeyForUser(user);
  const closedIds = readClosedConversationIds(storageKey);
  removeClosedRows(closedIds);

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.('.closeButton__972a0[role="button"]');
    if (!button || !button.closest('.privateChannels_e6b769')) return;
    event.preventDefault();
    event.stopPropagation();
    closeDirectMessage(button, storageKey, closedIds);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const button = event.target.closest?.('.closeButton__972a0[role="button"]');
    if (!button || !button.closest('.privateChannels_e6b769')) return;
    event.preventDefault();
    event.stopPropagation();
    closeDirectMessage(button, storageKey, closedIds);
  });
}
