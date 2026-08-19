const HTML_MIME = "text/html";
const Parser = new DOMParser();
const BLOCKED_ELEMENTS = new Set(["SCRIPT", "IFRAME", "OBJECT", "EMBED", "BASE"]);
const URL_ATTRIBUTES = new Set(["href", "src", "xlink:href", "formaction"]);

function assertTrustedTree(root) {
  const elements = root.querySelectorAll("*");
  for (const element of elements) {
    if (BLOCKED_ELEMENTS.has(element.tagName)) {
      throw new TypeError(`Elemento não permitido em markup de aplicação: ${element.tagName}`);
    }
    for (const attribute of element.attributes) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      if (name.startsWith("on") || name === "srcdoc") {
        throw new TypeError(`Atributo executável não permitido: ${attribute.name}`);
      }
      if (URL_ATTRIBUTES.has(name) && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
        throw new TypeError(`URL executável não permitida em ${attribute.name}`);
      }
    }
  }
}

function parseDocument(markup) {
  const parsed = Parser.parseFromString(String(markup ?? ""), HTML_MIME);
  assertTrustedTree(parsed.body);
  return parsed;
}

/**
 * Parse application-owned markup through one native, inert DOMParser boundary.
 *
 * Untrusted values must be written with textContent/value or escaped before a
 * trusted template string is passed here. The central boundary rejects script
 * containers, inline event handlers, srcdoc and executable URL schemes.
 */
export function trustedFragment(markup) {
  const parsed = parseDocument(markup);
  const fragment = document.createDocumentFragment();
  while (parsed.body.firstChild) {
    fragment.appendChild(document.adoptNode(parsed.body.firstChild));
  }
  return fragment;
}

export function trustedElement(markup) {
  const fragment = trustedFragment(markup);
  return fragment.firstElementChild || null;
}

export function replaceTrustedChildren(target, markup) {
  if (!target) return null;
  const fragment = trustedFragment(markup);
  target.replaceChildren(fragment);
  return target;
}

export function appendTrustedChildren(target, markup) {
  if (!target) return null;
  target.appendChild(trustedFragment(markup));
  return target;
}

export function escapeMarkup(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
