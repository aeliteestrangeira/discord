let active = null;

function normalize(entry) {
  if (!entry || typeof entry !== "object") return null;
  const id = String(entry.id || "").trim();
  const type = entry.type === "modal" ? "modal" : "menu";
  const close = typeof entry.close === "function" ? entry.close : null;
  if (!id || !close) return null;
  return { id, type, close };
}

export const OverlayManager = Object.freeze({
  claim(entry) {
    const next = normalize(entry);
    if (!next) throw new TypeError("Overlay inválido.");
    if (active && active.id !== next.id) {
      const previous = active;
      active = null;
      previous.close({ immediate: true, reason: "replaced" });
    }
    active = next;
    return next;
  },

  release(id) {
    if (active?.id === id) active = null;
  },

  closeTop(options = {}) {
    if (!active) return false;
    const previous = active;
    active = null;
    previous.close({ ...options, reason: options.reason || "close-top" });
    return true;
  },

  current() {
    return active ? Object.freeze({ id: active.id, type: active.type }) : null;
  },

  isActive(id) {
    return active?.id === id;
  },
});
