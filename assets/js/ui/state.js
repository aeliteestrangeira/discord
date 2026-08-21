const allowedKeys = new Set([
  "actor",
  "page",
  "status",
  "dateOfBirth",
  "marketingOptIn",
]);

const moduleRootUrl = new URL("../", import.meta.url);
const appRootUrl = /\/runtime\/[a-f0-9]{16}\/$/.test(moduleRootUrl.pathname)
  ? new URL("../../", moduleRootUrl)
  : moduleRootUrl;
const appRootPath = appRootUrl.pathname.toLowerCase();
const locationPath = location.pathname.toLowerCase();
const initialPath = locationPath.startsWith(appRootPath)
  ? `/${locationPath.slice(appRootPath.length)}`
  : locationPath;
const routeName = initialPath.split("/").filter(Boolean).at(-1) || "";
const isChannelsPath = routeName === "channels"
  || routeName === "channels.html"
  || initialPath.startsWith("/channels/");

let snapshot = Object.freeze({
  actor: "anonymous-user",
  page: isChannelsPath ? "channels" : (initialPath.includes("register") ? "register" : "login"),
  status: "idle",
  dateOfBirth: null,
  marketingOptIn: null,
});

const history = [];
const HISTORY_LIMIT = 64;

function commit(patch, cause = "ui") {
  const next = { ...snapshot };
  for (const [key, value] of Object.entries(patch || {})) {
    if (!allowedKeys.has(key)) throw new TypeError(`Estado desconhecido: ${key}`);
    next[key] = value;
  }
  snapshot = Object.freeze(next);
  history.push(Object.freeze({ cause, keys: Object.freeze(Object.keys(patch || {})), at: Date.now() }));
  if (history.length > HISTORY_LIMIT) history.shift();
  document.dispatchEvent(new CustomEvent("app:state-transition", {
    detail: Object.freeze({ cause, state: snapshot }),
  }));
  return snapshot;
}

export const State = new Proxy(Object.create(null), {
  get(_target, property) {
    if (property === "snapshot") return snapshot;
    if (property === "history") return Object.freeze([...history]);
    return snapshot[property];
  },
  set(_target, property, value) {
    if (typeof property !== "string" || !allowedKeys.has(property)) {
      throw new TypeError(`Estado desconhecido: ${String(property)}`);
    }
    commit({ [property]: value }, `property:${property}`);
    return true;
  },
  ownKeys() {
    return Reflect.ownKeys(snapshot);
  },
  getOwnPropertyDescriptor(_target, property) {
    if (Object.prototype.hasOwnProperty.call(snapshot, property)) {
      return { enumerable: true, configurable: true, value: snapshot[property] };
    }
    return undefined;
  },
});

export function transitionState(patch, cause = "ui") {
  return commit(patch, cause);
}

export function stateSnapshot() {
  return snapshot;
}

Object.defineProperty(window, "__APP_STATE__", {
  get: stateSnapshot,
  configurable: false,
  enumerable: false,
});
