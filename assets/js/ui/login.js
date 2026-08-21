import { State } from "./state.js";
import { emit, ensureAuthProvider, navigate, setBusy, textOf } from "./runtime.js";
import { OverlayManager } from "./overlay-manager.js";
import { replaceTrustedChildren } from "./dom.js";

function modalLayer() {
  const layers = [...document.querySelectorAll(".layerContainer__59d0d")];
  let layer = layers.reverse().find((candidate) => candidate.childElementCount === 0);
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "layerContainer__59d0d";
    document.body.appendChild(layer);
  }
  return layer;
}

async function requestLoginCaptchaToken() {
  const { requestCaptchaToken } = await import("./captcha.js");
  return requestCaptchaToken();
}

function loginCredentialErrorUi(form) {
  const identifier = form?.elements.namedItem("email");
  const password = form?.elements.namedItem("password");
  if (!identifier || !password) return null;

  const identifierField = identifier.closest(".container__5a838");
  const passwordField = password.closest(".container__5a838");
  const identifierControl = identifierField?.querySelector(".control__5a838");
  const passwordControl = passwordField?.querySelector(".control__5a838");
  const identifierVisual = identifier.closest(".input__0ed4f.input_d64f22");
  const passwordVisual = password.closest(".wrapper__72c38.container__75098");
  if (!identifierField || !passwordField || !identifierControl || !passwordControl || !identifierVisual || !passwordVisual) return null;

  const errorSvg = '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent" class=""></circle><path fill="var(--text-feedback-critical)" fill-rule="evenodd" d="M12 23a11 11 0 1 0 0-22 11 11 0 0 0 0 22Zm1.44-15.94L13.06 14a1.06 1.06 0 0 1-2.12 0l-.38-6.94a1 1 0 0 1 1-1.06h.88a1 1 0 0 1 1 1.06Zm-.19 10.69a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" clip-rule="evenodd" class=""></path></svg>';
  const ids = Object.freeze({ identifier: "app-login-identifier-error", password: "app-login-password-error" });

  function helper(id, message) {
    const outer = document.createElement("div");
    outer.className = "helperTextContainer__5a838";
    outer.dataset.appLoginError = "true";
    const status = document.createElement("div");
    status.className = "statusMessageContainer__5a838";
    status.setAttribute("role", "alert");
    replaceTrustedChildren(status, `${errorSvg}<div class="text-xs/normal_cf4812" id="${id}" data-text-variant="text-xs/normal" style="color: var(--text-feedback-critical);"></div>`);
    status.querySelector(`#${id}`).textContent = message;
    outer.appendChild(status);
    return outer;
  }

  function clearIdentifier() {
    identifierVisual.classList.remove("error__0ed4f");
    identifier.removeAttribute("aria-errormessage");
    identifier.removeAttribute("aria-invalid");
    identifierControl.querySelector('[data-app-login-error="true"]')?.remove();
  }

  function clearPassword() {
    passwordVisual.setAttribute("data-error", "false");
    password.setAttribute("aria-invalid", "false");
    password.removeAttribute("aria-errormessage");
    passwordControl.querySelector('[data-app-login-error="true"]')?.remove();
  }

  function clear() {
    clearIdentifier();
    clearPassword();
  }

  function showIdentifier(message) {
    clearIdentifier();
    identifierVisual.classList.add("error__0ed4f");
    // The captured identifier error state uses the visual error class and
    // helper row without adding aria-invalid/aria-errormessage to this input.
    identifierControl.appendChild(helper(ids.identifier, message));
  }

  function showCredentialDenied() {
    clear();
    const message = "Login ou senha inválidos.";

    identifierVisual.classList.add("error__0ed4f");
    identifierControl.appendChild(helper(ids.identifier, message));

    passwordVisual.setAttribute("data-error", "true");
    password.setAttribute("aria-invalid", "true");
    password.setAttribute("aria-errormessage", ids.password);
    passwordControl.appendChild(helper(ids.password, message));
  }

  function showIdentifierRequired() {
    clear();
    showIdentifier("Este campo é obrigatório.");
  }

  identifier.addEventListener("input", clearIdentifier);
  password.addEventListener("input", clearPassword);
  return Object.freeze({ showCredentialDenied, showIdentifierRequired, showIdentifier, clear, clearIdentifier, clearPassword });
}

function loginLinkModalMarkup(channel = "email") {
  const email = channel !== "phone";
  const title = email ? "Verifique seu e-mail para acessar com um link" : "Verifique seu telefone para acessar";
  const body = email
    ? "Toque no link enviado para seu e-mail para entrar instantaneamente — sem precisar de senha."
    : "Confira a mensagem enviada para seu telefone e use o código recebido para continuar.";
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c">
      <div id="app-login-link-dialog" aria-label="${title}" data-dialog="modal" role="dialog" aria-modal="true" tabindex="-1">
        <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border:0;clip:rect(0px,0px,0px,0px);clip-path:inset(50%);height:1px;margin:-1px;overflow:hidden;padding:0;position:absolute;width:1px;white-space:nowrap;"><div role="log" aria-live="assertive" aria-relevant="additions"></div><div role="log" aria-live="polite" aria-relevant="additions"></div></div></span>
        <div class="outerContainer__8a031 fullScreenOnMobile__8a031">
          <div data-mana-component="modal" class="container__8a031 size-md__8a031 padding-size-sm__8a031" style="opacity:1;transform:scale(1);">
            <header class="section__8a031 header__8a031">
              <div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap:var(--space-8);padding:var(--space-0);">
                <div class="headerLayout__8a031">
                  <div class="headerMain__8a031"><h1 class="heading-lg/semibold_cf4812 defaultColor__5345c headerTitle__8a031" data-text-variant="heading-lg/semibold" style="color:var(--text-strong);">${title}</h1></div>
                  <div class="headerTrailing__8a031"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 icon-only_a22cb0" type="button" aria-label="Fechar" data-login-link-close="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><svg class="icon_a22cb0" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M19.3 20.7a1 1 0 0 0 1.4-1.4L13.42 12l7.3-7.3a1 1 0 0 0-1.42-1.4L12 10.58l-7.3-7.3a1 1 0 0 0-1.4 1.42L10.58 12l-7.3 7.3a1 1 0 1 0 1.42 1.4L12 13.42l7.3 7.3Z" class=""></path></svg></div></div></button></div>
                </div>
              </div>
            </header>
            <div class="sectionHidden__8a031 section__8a031"><div class="container__35859 info__35859 hidden__35859"><div class="innerContainer__35859"><div class="iconDiv__35859"><svg class="icon__35859" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent" class=""></circle><path fill="currentColor" fill-rule="evenodd" d="M23 12a11 11 0 1 1-22 0 11 11 0 0 1 22 0Zm-9.5-4.75a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Zm-.77 3.96a1 1 0 1 0-1.96-.42l-1.04 4.86a2.77 2.77 0 0 0 4.31 2.83l.24-.17a1 1 0 1 0-1.16-1.62l-.24.17a.77.77 0 0 1-1.2-.79l1.05-4.86Z" clip-rule="evenodd" class=""></path></svg></div><div class="text-sm/medium_cf4812 text__35859" data-text-variant="text-sm/medium" style="color:var(--text-default);"></div></div></div></div>
            <div class="bodySpacerTop__8a031"></div>
            <div class="body__8a031 scrollbarGutterStable_d125d2 auto_d125d2 scrollerBase_d125d2" dir="ltr" style="overflow:hidden scroll;"><main class="bodyInner__8a031"><div class="defaultColor__4bd52 text-md/normal_cf4812" data-text-variant="text-md/normal">${body}</div></main></div>
            <div class="bodySpacerBottom__8a031"></div>
            <footer class="actionBar__8a031 section__8a031"><div class="actionBarTrailing__8a031 actionBarTrailingFullWidth__8a031"><div data-align="stretch" data-justify="start" data-direction="horizontal" data-wrap="true" data-full-width="true" class="stack_dbd263" style="gap:var(--space-8);padding:var(--space-0);"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button" data-login-link-okay="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">OK</span></div></div></button></div></div></footer>
          </div>
        </div>
      </div>
    </div>`;
}

function showLoginLinkModal(channel = "email") {
  const layer = modalLayer();
  replaceTrustedChildren(layer, loginLinkModalMarkup(channel));
  const dialog = layer.querySelector("#app-login-link-dialog");
  const previousFocus = document.activeElement;

  const cleanup = () => {
    document.removeEventListener("keydown", onKeyDown, true);
    layer.replaceChildren();
    OverlayManager.release("login-link");
    if (previousFocus && typeof previousFocus.focus === "function") {
      requestAnimationFrame(() => previousFocus.focus({ preventScroll: true }));
    }
  };
  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      cleanup();
    }
  };

  OverlayManager.claim({ id: "login-link", type: "modal", close: cleanup });
  layer.querySelector('[data-login-link-close="true"]')?.addEventListener("click", cleanup, { once: true });
  layer.querySelector('[data-login-link-okay="true"]')?.addEventListener("click", cleanup, { once: true });
  document.addEventListener("keydown", onKeyDown, true);
  requestAnimationFrame(() => dialog?.focus({ preventScroll: true }));
}

function wireForgotPassword(credentialErrors) {
  if (State.page !== "login") return;
  const form = document.querySelector("form");
  const identifier = form?.elements.namedItem("email");
  if (!form || !identifier) return;

  const button = [...form.querySelectorAll('button[type="button"]')].find((candidate) => textOf(candidate) === "Esqueceu sua senha?");
  if (!button) return;

  button.addEventListener("click", async () => {
    const value = identifier.value.trim();
    credentialErrors?.clear();
    if (!value) {
      State.status = "invalid";
      credentialErrors?.showIdentifierRequired();
      identifier.focus({ preventScroll: true });
      return;
    }

    if (button.getAttribute("aria-busy") === "true") return;
    button.setAttribute("aria-busy", "true");
    State.status = "requesting-login-link";
    try {
      const authProvider = await ensureAuthProvider();
      const hcaptchaToken = location.origin === "https://aeliteestrangeira.github.io"
        ? await requestLoginCaptchaToken()
        : "";
      const result = await authProvider.requestLoginLink(value, hcaptchaToken);
      if (!result.configured) {
        State.status = "ready-for-auth-provider";
        emit("app:auth-unconfigured", { type: "login-link" });
        return;
      }
      if (result.error) {
        State.status = "auth-error";
        emit("app:auth-error", { type: "login-link", error: result.error });
        return;
      }
      State.status = "login-link-requested";
      showLoginLinkModal(result.data?.channel || (value.includes("@") ? "email" : "phone"));
      emit("app:login-link-requested", { channel: result.data?.channel || "unknown" });
    } catch (error) {
      State.status = "auth-error";
      emit("app:auth-error", { type: "login-link", error });
    } finally {
      button.setAttribute("aria-busy", "false");
    }
  });
}


function base64UrlToBytes(value) {
  const normalized = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function bytesToBase64Url(value) {
  const bytes = value instanceof ArrayBuffer ? new Uint8Array(value) : new Uint8Array(value?.buffer || value || []);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function parsePasskeyRequestOptions(options) {
  if (window.PublicKeyCredential?.parseRequestOptionsFromJSON) {
    return window.PublicKeyCredential.parseRequestOptionsFromJSON(options);
  }
  const parsed = { ...options, challenge: base64UrlToBytes(options.challenge) };
  if (Array.isArray(options.allowCredentials)) {
    parsed.allowCredentials = options.allowCredentials.map((item) => ({ ...item, id: base64UrlToBytes(item.id) }));
  }
  return parsed;
}

function passkeyCredentialToJSON(credential) {
  if (typeof credential?.toJSON === "function") return credential.toJSON();
  const response = credential?.response;
  return {
    id: credential?.id || "",
    rawId: bytesToBase64Url(credential?.rawId),
    type: credential?.type || "public-key",
    authenticatorAttachment: credential?.authenticatorAttachment || null,
    clientExtensionResults: typeof credential?.getClientExtensionResults === "function" ? credential.getClientExtensionResults() : {},
    response: {
      clientDataJSON: bytesToBase64Url(response?.clientDataJSON),
      authenticatorData: bytesToBase64Url(response?.authenticatorData),
      signature: bytesToBase64Url(response?.signature),
      userHandle: response?.userHandle ? bytesToBase64Url(response.userHandle) : null
    }
  };
}

function wirePasskeyLogin() {
  if (State.page !== "login") return;
  const form = document.querySelector("form");
  const identifier = form?.elements.namedItem("email");
  const explicitButton = [...(form?.querySelectorAll('button[type="button"]') || [])]
    .find((candidate) => textOf(candidate) === "Ou, entre com uma chave de acesso");
  if (!form || !identifier || !explicitButton) return;

  let conditionalController = null;
  let conditionalGeneration = 0;
  let rearmTimer = null;

  async function providerOptions() {
    const authProvider = await ensureAuthProvider();
    const result = await authProvider.startPasskeyAuthentication();
    if (!result.configured || result.error || !result.data?.options || !result.data?.challengeId) {
      const error = new Error(result.error?.message || "Chaves de acesso indisponíveis.");
      error.code = result.error?.code || "passkey_unavailable";
      throw error;
    }
    return result.data;
  }

  async function finishPasskey(data, credential, source) {
    const authProvider = await ensureAuthProvider();
    const result = await authProvider.verifyPasskeyAuthentication(data.challengeId, passkeyCredentialToJSON(credential));
    if (!result.configured || result.error) {
      const error = new Error(result.error?.message || "A chave de acesso não foi aceita.");
      error.code = result.error?.code || "passkey_verify_error";
      throw error;
    }
    State.status = "authenticated";
    emit("app:auth-success", { type: "passkey", source, data: result.data });
    navigate(result.data?.redirect || "/channels/@me");
    return result.data;
  }

  function cancelConditional() {
    conditionalGeneration += 1;
    if (rearmTimer) {
      clearTimeout(rearmTimer);
      rearmTimer = null;
    }
    conditionalController?.abort();
    conditionalController = null;
  }

  function scheduleConditional(delay = 250) {
    if (rearmTimer) clearTimeout(rearmTimer);
    rearmTimer = setTimeout(() => {
      rearmTimer = null;
      armConditional().catch(() => {});
    }, delay);
  }

  async function armConditional() {
    cancelConditional();
    if (!window.isSecureContext || !navigator.credentials || !window.PublicKeyCredential) return;
    if (typeof window.PublicKeyCredential.isConditionalMediationAvailable !== "function") return;
    if (!(await window.PublicKeyCredential.isConditionalMediationAvailable())) return;

    const generation = conditionalGeneration;
    let data;
    try {
      data = await providerOptions();
    } catch (error) {
      emit("app:passkey-unavailable", { source: "conditional", code: error?.code || "passkey_unavailable" });
      return;
    }
    if (generation !== conditionalGeneration) return;

    const controller = new AbortController();
    conditionalController = controller;
    try {
      const credential = await navigator.credentials.get({
        publicKey: parsePasskeyRequestOptions(data.options),
        mediation: "conditional",
        signal: controller.signal
      });
      if (!credential || controller.signal.aborted) return;
      conditionalController = null;
      await finishPasskey(data, credential, "conditional");
    } catch (error) {
      if (error?.name !== "AbortError" && error?.name !== "NotAllowedError") {
        emit("app:passkey-error", { source: "conditional", code: error?.code || error?.name || "passkey_error" });
      }
    } finally {
      if (conditionalController === controller) conditionalController = null;
    }
  }

  explicitButton.addEventListener("click", async () => {
    if (explicitButton.getAttribute("aria-busy") === "true") return;
    cancelConditional();
    explicitButton.setAttribute("aria-busy", "true");
    State.status = "authenticating-passkey";
    let authenticated = false;
    try {
      if (!window.isSecureContext || !navigator.credentials || !window.PublicKeyCredential) {
        const error = new Error("Chaves de acesso exigem HTTPS.");
        error.code = "secure_context_required";
        throw error;
      }
      const data = await providerOptions();
      const credential = await navigator.credentials.get({
        publicKey: parsePasskeyRequestOptions(data.options),
        mediation: "required"
      });
      if (!credential) return;
      await finishPasskey(data, credential, "explicit");
      authenticated = true;
    } catch (error) {
      if (error?.name === "NotAllowedError" || error?.name === "AbortError") {
        State.status = "idle";
        emit("app:passkey-cancelled", { type: "passkey" });
      } else {
        State.status = "auth-error";
        emit("app:passkey-error", { source: "explicit", code: error?.code || error?.name || "passkey_error" });
      }
    } finally {
      explicitButton.setAttribute("aria-busy", "false");
      // A modal WebAuthn request and a conditional request cannot remain
      // active at the same time. Re-arm conditional mediation after Cancel
      // so focusing the username field offers passkeys again without reload.
      if (!authenticated) scheduleConditional(300);
    }
  });

  // The input already carries autocomplete="username webauthn" in the
  // captured HTML. The pending conditional request lets the browser render
  // its own native passkey suggestion UI when that field receives focus.
  scheduleConditional(0);
  window.addEventListener("pagehide", cancelConditional, { once: true });
}

function wireLoginForm() {
  if (State.page !== "login") return;
  const form = document.querySelector("form");
  if (!form) return;
  const credentialErrors = loginCredentialErrorUi(form);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    if (submit?.getAttribute("aria-busy") === "true") return;
    credentialErrors?.clear();
    if (!form.checkValidity()) {
      State.status = "invalid";
      form.reportValidity();
      return;
    }

    const identifier = form.elements.namedItem("email")?.value?.trim() || "";
    const password = form.elements.namedItem("password")?.value || "";
    State.status = "authenticating";
    setBusy(form, true);

    try {
      const hcaptchaToken = await requestLoginCaptchaToken();
      const authProvider = await ensureAuthProvider();
      const result = await authProvider.signIn(identifier, password, hcaptchaToken);
      if (!result.configured) {
        State.status = "ready-for-auth-provider";
        emit("app:auth-unconfigured", { type: "login" });
        return;
      }
      if (result.error) {
        State.status = "auth-error";
        if (result.error.code === "auth_denied") {
          credentialErrors?.showCredentialDenied();
        }
        emit("app:auth-error", { type: "login", error: result.error });
        return;
      }
      State.status = "authenticated";
      emit("app:auth-success", { type: "login", data: result.data });
      if (result.data?.role === "admin" && result.data?.redirect === "/admin") {
        navigate("/admin");
      } else {
        navigate(result.data?.redirect || "/channels/@me");
      }
    } catch (error) {
      if (error?.name === "AbortError") {
        State.status = "idle";
        emit("app:captcha-cancelled", { type: "login" });
      } else {
        State.status = "auth-error";
        emit("app:auth-error", { type: "login", error });
      }
    } finally {
      setBusy(form, false);
    }
  });
  return credentialErrors;
}

export { wireForgotPassword, wirePasskeyLogin, wireLoginForm };
