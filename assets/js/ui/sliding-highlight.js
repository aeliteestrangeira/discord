const transition = "transform 120ms cubic-bezier(0.2, 0, 0, 1), height 120ms cubic-bezier(0.2, 0, 0, 1)";

export const SlidingHighlightController = Object.freeze({
  create({ attribute = "data-app-sliding-highlight", value = "true" } = {}) {
    const highlight = document.createElement("div");
    highlight.setAttribute(attribute, value);
    highlight.setAttribute("aria-hidden", "true");
    highlight.style.position = "absolute";
    highlight.style.left = "0";
    highlight.style.right = "0";
    highlight.style.top = "0";
    highlight.style.height = "40px";
    highlight.style.borderRadius = "var(--radius-xs)";
    highlight.style.backgroundColor = "var(--background-mod-normal)";
    highlight.style.pointerEvents = "none";
    highlight.style.opacity = "0";
    highlight.style.transform = "translate3d(0, 0, 0)";
    highlight.style.willChange = "transform";
    highlight.style.transition = "none";
    highlight.style.zIndex = "0";
    return highlight;
  },

  ensureSingle(container, options = {}) {
    if (!container) return null;
    const selector = `[${options.attribute || "data-app-sliding-highlight"}]`;
    const existing = [...container.querySelectorAll(selector)];
    const highlight = existing.shift() || this.create(options);
    existing.forEach((candidate) => candidate.remove());
    if (!highlight.isConnected) container.prepend(highlight);
    return highlight;
  },

  move({ item, highlight, immediate = false }) {
    if (!item || !highlight) return;
    const targetY = item.offsetTop;
    const targetHeight = item.offsetHeight || 40;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;

    highlight.style.opacity = "1";
    highlight.style.height = `${targetHeight}px`;
    if (immediate || reducedMotion) {
      highlight.style.transition = "none";
      highlight.style.transform = `translate3d(0, ${targetY}px, 0)`;
      void highlight.offsetHeight;
      highlight.style.transition = reducedMotion ? "none" : transition;
    } else {
      highlight.style.transition = transition;
      highlight.style.transform = `translate3d(0, ${targetY}px, 0)`;
    }
  },

  hide(highlight, { immediate = false } = {}) {
    if (!highlight) return;
    if (immediate) highlight.style.transition = "none";
    highlight.style.opacity = "0";
  },
});
