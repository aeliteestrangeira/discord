import { State } from "./state.js";
import { replaceTrustedChildren } from "./dom.js";

const APP_ROOT_URL = new URL("../", import.meta.url);

export function appUrl(target) {
  const raw = String(target || "").trim();
  if (!raw) return APP_ROOT_URL.href;
  if (/^[a-z][a-z0-9+.-]*:/i.test(raw) || raw.startsWith("//")) return new URL(raw, APP_ROOT_URL).href;
  return new URL(raw.startsWith("/") ? raw.slice(1) : raw, APP_ROOT_URL).href;
}

export function textOf(button) {
  return (button?.textContent || "").replace(/\s+/g, " ").trim();
}

export function emit(name, detail = {}) {
  document.dispatchEvent(new CustomEvent(name, {
    detail: Object.freeze({ ...detail, page: State.page, status: State.status }),
  }));
}

export function setButtonBusy(button, busy) {
  if (!button) return;
  button.setAttribute("aria-busy", busy ? "true" : "false");

  const wrapper = button.querySelector(".buttonChildrenWrapper_a22cb0");
  const children = wrapper?.querySelector(".buttonChildren_a22cb0");
  let spinner = wrapper?.querySelector(".spinnerWrapper_a22cb0");

  if (busy) {
    children?.classList.add("loading_a22cb0");
    if (wrapper && !spinner) {
      spinner = document.createElement("div");
      spinner.className = "spinnerWrapper_a22cb0 fadeIn_a22cb0";
      replaceTrustedChildren(spinner, '<span class="spinner__46696 spinner_a22cb0 spinner-md_a22cb0" role="img" aria-label="Carregando"><span class="inner__46696 pulsingEllipsis__46696"><span class="item__46696 spinnerItem_a22cb0"></span><span class="item__46696 spinnerItem_a22cb0"></span><span class="item__46696 spinnerItem_a22cb0"></span></span></span>');
      wrapper.appendChild(spinner);
    }
    return;
  }

  children?.classList.remove("loading_a22cb0");
  if (spinner) {
    spinner.classList.remove("fadeIn_a22cb0");
    spinner.classList.add("fadeOut_a22cb0");
    window.setTimeout(() => spinner?.remove(), 220);
  }
}

export function setBusy(form, busy) {
  setButtonBusy(form?.querySelector('button[type="submit"]'), busy);
}

function inputFocusContainers() {
  return document.querySelectorAll(".input__0ed4f.input_d64f22");
}

export function clearInitialFocus() {
  if (State.page !== "login") return;

  const active = document.activeElement;
  if (active && active !== document.body && typeof active.blur === "function") active.blur();
  for (const container of inputFocusContainers()) container.classList.remove("focused__0ed4f");
}

export function wireInputFocusStates() {
  for (const container of inputFocusContainers()) {
    container.classList.remove("focused__0ed4f");
    container.addEventListener("focusin", () => container.classList.add("focused__0ed4f"));
    container.addEventListener("focusout", () => {
      requestAnimationFrame(() => {
        if (!container.contains(document.activeElement)) container.classList.remove("focused__0ed4f");
      });
    });
  }
}

let authProviderPromise;

export function ensureAuthProvider() {
  if (window.AppAuthProvider) return Promise.resolve(window.AppAuthProvider);
  if (authProviderPromise) return authProviderPromise;

  authProviderPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-app-auth-provider="true"]');
    if (existing) {
      existing.addEventListener("load", () => resolve(window.AppAuthProvider), { once: true });
      existing.addEventListener("error", () => reject(new Error("Falha ao carregar o provedor de autenticação.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = new URL("auth-provider.js", APP_ROOT_URL).href;
    script.async = true;
    script.dataset.appAuthProvider = "true";
    script.addEventListener("load", () => {
      if (!window.AppAuthProvider) {
        reject(new Error("Provedor de autenticação indisponível."));
        return;
      }
      resolve(window.AppAuthProvider);
    }, { once: true });
    script.addEventListener("error", () => reject(new Error("Falha ao carregar o provedor de autenticação.")), { once: true });
    document.head.appendChild(script);
  });

  return authProviderPromise;
}

export function navigate(target) {
  State.status = "navigating";
  location.assign(appUrl(target));
}

export function wireNavigation() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const label = textOf(button);
    if (State.page === "login" && label === "Cadastre-se") {
      event.preventDefault();
      navigate("/register.html");
    }
    if (State.page === "register" && label === "Já tem uma conta? Entrar") {
      event.preventDefault();
      navigate("/");
    }
  });
}
