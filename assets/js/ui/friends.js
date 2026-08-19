import { showVerificationRequired } from "./account-verification.js";
import { OverlayManager } from "./overlay-manager.js";
import { emit, setBusy } from "./runtime.js";
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

function closeIcon() {
  return '<svg class="icon_a22cb0" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M19.3 20.7a1 1 0 0 0 1.4-1.4L13.42 12l7.3-7.3a1 1 0 0 0-1.42-1.4L12 10.58l-7.3-7.3a1 1 0 0 0-1.4 1.42L10.58 12l-7.3 7.3a1 1 0 1 0 1.42 1.4L12 13.42l7.3 7.3Z"></path></svg>';
}

function failureModalMarkup(message) {
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c"><div id="app-friend-request-failed" aria-label="Falha ao enviar pedido de amizade" data-dialog="modal" role="dialog" aria-modal="true" tabindex="-1">
      <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border: 0px; clip: rect(0px, 0px, 0px, 0px); clip-path: inset(50%); height: 1px; margin: -1px; overflow: hidden; padding: 0px; position: absolute; width: 1px; white-space: nowrap;"><div role="log" aria-live="assertive" aria-relevant="additions"></div><div role="log" aria-live="polite" aria-relevant="additions"></div></div></span>
      <div class="outerContainer__8a031 fullScreenOnMobile__8a031"><div data-mana-component="modal" class="container__8a031 size-sm__8a031 padding-size-sm__8a031" style="opacity: 1; transform: scale(1);">
        <header class="section__8a031 header__8a031"><div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);"><div class="headerLayout__8a031"><div class="headerMain__8a031"><h1 class="heading-lg/semibold_cf4812 defaultColor__5345c headerTitle__8a031" data-text-variant="heading-lg/semibold" style="color: var(--text-strong);">Falha ao enviar pedido de amizade</h1></div><div class="headerTrailing__8a031"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 icon-only_a22cb0" type="button" aria-label="Fechar"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0">${closeIcon()}</div></div></button></div></div><div class="headerSubtitleWrapper__8a031"><div class="text-md/normal_cf4812 headerSubtitle__8a031" data-text-variant="text-md/normal" style="color: var(--text-subtle);"></div></div></div></header>
        <div class="sectionHidden__8a031 section__8a031"><div class="container__35859 info__35859 hidden__35859"><div class="innerContainer__35859"><div class="iconDiv__35859"><svg class="icon__35859" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent"></circle><path fill="currentColor" fill-rule="evenodd" d="M23 12a11 11 0 1 1-22 0 11 11 0 0 1 22 0Zm-9.5-4.75a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Zm-.77 3.96a1 1 0 1 0-1.96-.42l-1.04 4.86a2.77 2.77 0 0 0 4.31 2.83l.24-.17a1 1 0 1 0-1.16-1.62l-.24.17a.77.77 0 0 1-1.2-.79l1.05-4.86Z" clip-rule="evenodd"></path></svg></div><div class="text-sm/medium_cf4812 text__35859" data-text-variant="text-sm/medium" style="color: var(--text-default);"></div></div></div></div>
        <footer class="actionBar__8a031 section__8a031"><div class="actionBarTrailing__8a031 actionBarTrailingFullWidth__8a031"><div data-align="stretch" data-justify="start" data-direction="horizontal" data-wrap="true" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Ok</span></div></div></button></div></div></footer>
      </div></div>
    </div></div>`;
}

function showFailureModal(message) {
  const layer = modalLayer();
  replaceTrustedChildren(layer, failureModalMarkup(message));
  const subtitle = layer.querySelector(".headerSubtitle__8a031");
  if (subtitle) subtitle.textContent = message;
  const close = () => {
    layer.replaceChildren();
    OverlayManager.release("friend-request-failed");
  };
  OverlayManager.claim({ id: "friend-request-failed", type: "modal", close });
  const buttons = [...layer.querySelectorAll("button")];
  buttons[0]?.addEventListener("click", close, { once: true });
  buttons.at(-1)?.addEventListener("click", close, { once: true });
  requestAnimationFrame(() => layer.querySelector("#app-friend-request-failed")?.focus({ preventScroll: true }));
}

function clearFeedback(form, wrapper, input) {
  wrapper.classList.remove("error__72ba7", "success__72ba7");
  input.removeAttribute("aria-invalid");
  input.setAttribute("aria-describedby", "uid_2-decription");
  form.querySelector('[role="alert"]')?.remove();
  const status = form.querySelector('[role="status"]');
  if (status) status.replaceChildren();
}

function showInlineError(form, wrapper, input, message) {
  clearFeedback(form, wrapper, input);
  wrapper.classList.add("error__72ba7");
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", "uid_2-error");
  const alert = document.createElement("div");
  alert.setAttribute("role", "alert");
  const text = document.createElement("div");
  text.className = "text-sm/normal_cf4812 marginTop8_fd297e";
  text.id = "uid_2-error";
  text.dataset.textVariant = "text-sm/normal";
  text.style.color = "var(--text-feedback-critical)";
  text.textContent = message;
  alert.appendChild(text);
  const status = form.querySelector('[role="status"]');
  form.insertBefore(alert, status || null);
}

function showSuccess(form, wrapper, input, username) {
  clearFeedback(form, wrapper, input);
  wrapper.classList.add("success__72ba7");
  input.setAttribute("aria-describedby", "uid_2-decription");
  const status = form.querySelector('[role="status"]');
  if (!status) return;
  const text = document.createElement("div");
  text.className = "text-sm/normal_cf4812 marginTop8_fd297e";
  text.dataset.textVariant = "text-sm/normal";
  text.style.color = "var(--text-feedback-positive)";
  text.append("Sucesso! Seu pedido de amizade para ");
  const strong = document.createElement("strong");
  strong.textContent = username;
  text.append(strong, " foi enviado.");
  status.appendChild(text);
}

export function wireFriendRequests(authProvider) {
  const input = document.querySelector('input[name="add-friend"]');
  const form = input?.closest("form");
  const wrapper = form?.querySelector(".addFriendInputWrapper__72ba7");
  const submit = form?.querySelector('button[type="submit"]');
  if (!input || !form || !wrapper || !submit) return;

  let busy = false;
  let completedValue = "";
  const syncButton = () => {
    if (busy) return;
    const value = input.value.trim();
    submit.disabled = value.length === 0 || (completedValue && value === completedValue);
  };

  input.addEventListener("input", () => {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const lower = input.value.toLowerCase();
    if (lower !== input.value) {
      input.value = lower;
      try { input.setSelectionRange(start, end); } catch (_) {}
    }
    completedValue = "";
    clearFeedback(form, wrapper, input);
    syncButton();
  });
  syncButton();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = input.value.trim().toLowerCase();
    if (!username || busy) return;
    busy = true;
    submit.disabled = true;
    setBusy(form, true);
    clearFeedback(form, wrapper, input);
    try {
      const { requestCaptchaToken } = await import("./captcha.js");
      const hcaptchaToken = await requestCaptchaToken();
      const result = await authProvider.sendFriendRequest(username, hcaptchaToken);
      if (result.error) {
        if (result.error.code === "verification_required") {
          showVerificationRequired(authProvider);
          emit("app:friend-request-verification-required");
          return;
        }
        const message = result.error.code === "friend_username_not_found" || result.error.code === "friend_self_not_allowed" || result.error.code === "friend_request_conflict"
          ? "Hum, não funcionou. Confira se o nome de usuário está correto."
          : (result.error.message || "Hum, não funcionou. Confira se o nome de usuário está correto.");
        showInlineError(form, wrapper, input, message);
        showFailureModal(message);
        emit("app:friend-request-error", { code: result.error.code || "friend_request_error" });
        return;
      }
      const canonical = result.data?.request?.username || username;
      completedValue = input.value.trim();
      showSuccess(form, wrapper, input, canonical);
      emit("app:friend-request-success", { username: canonical });
    } catch (error) {
      if (error?.name !== "AbortError") {
        const message = "Não foi possível enviar o pedido de amizade agora.";
        showInlineError(form, wrapper, input, message);
        showFailureModal(message);
        emit("app:friend-request-error", { code: error?.name || "friend_request_error" });
      }
    } finally {
      busy = false;
      setBusy(form, false);
      syncButton();
    }
  });
}
