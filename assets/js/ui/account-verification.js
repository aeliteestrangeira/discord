import { OverlayManager } from "./overlay-manager.js";
import { appendTrustedChildren, replaceTrustedChildren } from "./dom.js";
import { appUrl, emit } from "./runtime.js";

const VERIFY_ASSET = "/assets/88cde2b0ab4c8015cee8fdb8732b85b01df4fc78a75b3aa5e621539ea94b1803.svg";
let activeLayer = null;
let activeAuthProvider = null;

function verificationLayer() {
  if (activeLayer?.isConnected) return activeLayer;
  const layers = [...document.querySelectorAll(".layerContainer__59d0d")];
  activeLayer = layers.reverse().find((candidate) => candidate.childElementCount === 0) || null;
  if (!activeLayer) {
    activeLayer = document.createElement("div");
    activeLayer.className = "layerContainer__59d0d";
    document.body.appendChild(activeLayer);
  }
  return activeLayer;
}

function closeVerificationFlow() {
  if (activeLayer) activeLayer.replaceChildren();
  OverlayManager.release("verification-required");
  activeLayer = null;
  activeAuthProvider = null;
}

function verificationRequiredMarkup() {
  return `
    <div class="root__5c9fc enterDone__5c9fc">
      <div class="drag__5c9fc"></div>
      <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263 verification_dede4b" style="gap: var(--space-16); padding: var(--space-0);">
        <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="false" class="stack_dbd263 container_dede4b" style="gap: var(--space-16); padding: var(--space-0);">
          <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-16); padding: var(--space-0);">
            <div class="image_dede4b"></div>
            <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263 textContainer_dede4b" style="gap: var(--space-4); padding: var(--space-0);">
              <h2 class="defaultColor__4bd52 heading-xl/normal_cf4812 defaultColor__5345c" data-text-variant="heading-xl/normal">Verificação necessária</h2>
              <div class="defaultColor__4bd52 text-md/normal_cf4812" data-text-variant="text-md/normal">Precisamos confirmar sua identidade para manter sua conta segura. Verifique sua conta para continuar usando o Discord. <a class="anchor_edefb8 anchorUnderlineOnHover_edefb8" href="https://support.discord.com/hc/en-us/articles/6181726888215" rel="noreferrer noopener" target="_blank">Saiba mais.</a></div>
            </div>
          </div>
          <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-16); padding: var(--space-0);">
            <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0" type="button"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Verificar por e-mail</span></div></div></button>
          </div>
        </div>
        <div data-align="center" data-justify="center" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
          <div class="defaultColor__4bd52 text-sm/normal_cf4812 footer_dede4b" data-text-variant="text-sm/normal">Acha que está vendo isso por engano?</div>
          <div data-align="center" data-justify="center" data-direction="horizontal" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
            <div class="defaultColor__4bd52 text-sm/semibold_cf4812 footer_dede4b" data-text-variant="text-sm/semibold"><a class="anchor_edefb8 anchorUnderlineOnHover_edefb8" href="https://support.discord.com/hc/en-us/requests/new?platform=" rel="noreferrer noopener" target="_blank">Suporte</a></div>
            <div class="footer_dede4b footerBullet_dede4b">•</div>
            <div class="defaultColor__4bd52 text-sm/semibold_cf4812 footer_dede4b" data-text-variant="text-sm/semibold"><a class="anchor_edefb8 anchorUnderlineOnHover_edefb8" role="link" tabindex="0">Sair</a></div>
          </div>
        </div>
      </div>
    </div>`;
}

function verifyByEmailMarkup() {
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c">
      <div id="app-verify-email-dialog" aria-label="Verificar por e-mail" data-dialog="modal" role="dialog" aria-modal="true" tabindex="-1">
        <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border: 0px; clip: rect(0px, 0px, 0px, 0px); clip-path: inset(50%); height: 1px; margin: -1px; overflow: hidden; padding: 0px; position: absolute; width: 1px; white-space: nowrap;"></div></span>
        <div class="outerContainer__8a031 fullScreenOnMobile__8a031">
          <div data-mana-component="modal" class="container__8a031 size-md__8a031 padding-size-lg__8a031" style="opacity: 1; transform: scale(1);">
            <div class="container_a62383 purple_a62383 headerGradient__8a031" style="--custom-gradient-offset-bottom: 0%;">
              <header class="section__8a031 header__8a031 headerCentered__8a031">
                <div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
                  <div class="headerLayout__8a031">
                    <div class="headerLeading__8a031 headerLeadingAbsolute__8a031"></div>
                    <div class="headerLeadingSpacer__8a031" style="height: 35px; width: 45px;"></div>
                    <div class="headerMain__8a031"><div class="headerGraphic__8a031"><div class="headerGraphicContainer__8a031"><div class="container__8ef77 aspect-ratio-16/9__8ef77"><img class="image__8ef77" alt="" draggable="false" src="${VERIFY_ASSET}"></div></div></div></div>
                    <div class="headerTrailingSpacer__8a031" style="height: 35px; width: 45px;"></div>
                  </div>
                  <h1 class="heading-xl/semibold_cf4812 defaultColor__5345c headerTitle__8a031" data-text-variant="heading-xl/semibold" style="color: var(--text-strong);">Verificar por e-mail</h1>
                  <div class="headerSubtitleWrapper__8a031"><div class="text-md/normal_cf4812 headerSubtitle__8a031" data-text-variant="text-md/normal" style="color: var(--text-subtle);">Verifique seu e-mail e siga as instruções para confirmar sua conta. Se você não recebeu um e-mail ou se ele expirou, pode reenviar outro.</div></div>
                </div>
              </header>
            </div>
            <footer class="actionBar__8a031 section__8a031"><div class="actionBarTrailing__8a031 actionBarTrailingFullWidth__8a031"><div data-align="stretch" data-justify="start" data-direction="horizontal" data-wrap="true" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
              <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 secondary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Reenviar e-mail</span></div></div></button>
              <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Alterar e-mail</span></div></div></button>
            </div></div></footer>
          </div>
        </div>
      </div>
    </div>`;
}

function closeIcon() {
  return '<svg class="icon_a22cb0" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M19.3 20.7a1 1 0 0 0 1.4-1.4L13.42 12l7.3-7.3a1 1 0 0 0-1.42-1.4L12 10.58l-7.3-7.3a1 1 0 0 0-1.4 1.42L10.58 12l-7.3 7.3a1 1 0 1 0 1.42 1.4L12 13.42l7.3 7.3Z"></path></svg>';
}

function changeEmailMarkup() {
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c">
      <div id="app-change-email-dialog" aria-label="Verificar por e-mail" data-dialog="modal" role="dialog" aria-modal="true" tabindex="-1">
        <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border: 0px; clip: rect(0px, 0px, 0px, 0px); clip-path: inset(50%); height: 1px; margin: -1px; overflow: hidden; padding: 0px; position: absolute; width: 1px; white-space: nowrap;"></div></span>
        <div class="outerContainer__8a031 fullScreenOnMobile__8a031">
          <div data-mana-component="modal" class="container__8a031 size-md__8a031 padding-size-lg__8a031" style="opacity: 1; transform: scale(1);">
            <div class="container_a62383 purple_a62383 headerGradient__8a031" style="--custom-gradient-offset-bottom: 0%;">
              <header class="section__8a031 header__8a031 headerCentered__8a031"><div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);">
                <div class="headerLayout__8a031">
                  <div class="headerLeading__8a031 headerLeadingAbsolute__8a031"></div><div class="headerLeadingSpacer__8a031" style="height: 35px; width: 45px;"></div>
                  <div class="headerMain__8a031"><div class="headerGraphic__8a031"><div class="headerGraphicContainer__8a031"><div class="container__8ef77 aspect-ratio-16/9__8ef77"><img class="image__8ef77" alt="" draggable="false" src="${VERIFY_ASSET}"></div></div></div></div>
                  <div class="headerTrailingSpacer__8a031" style="height: 35px; width: 45px;"></div>
                  <div class="headerTrailing__8a031 headerTrailingAbsolute__8a031"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 color-mix_a22cb0" type="button" aria-label="Fechar"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0">${closeIcon()}</div></div></button></div>
                </div>
                <h1 class="heading-xl/semibold_cf4812 defaultColor__5345c headerTitle__8a031" data-text-variant="heading-xl/semibold" style="color: var(--text-strong);">Verificar por e-mail</h1>
                <div class="headerSubtitleWrapper__8a031"><div class="text-md/normal_cf4812 headerSubtitle__8a031" data-text-variant="text-md/normal" style="color: var(--text-subtle);">Para verificar seu endereço de e-mail, primeiro você deve inserir um endereço de e-mail.</div></div>
              </div></header>
            </div>
            <div class="bodySpacerTop__8a031 bodySpacerTopBorder__8a031"></div>
            <div class="body__8a031 scrollbarGutterStable_d125d2 auto_d125d2 scrollerBase_d125d2" dir="ltr" style="overflow: hidden scroll;"><main class="bodyInner__8a031 bodyInnerShouldScroll__8a031"><div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-40); padding-bottom: var(--space-8);"><div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap: var(--space-20); padding: var(--space-0);">
              <div class="container__5a838" data-layout="vertical"><div class="labelContainer__5a838"><label class="text-md/medium_cf4812 label__5a838" aria-hidden="false" data-interactive="false" for="app-change-email" data-text-variant="text-md/medium" style="color: var(--text-strong);">E-mail</label></div><div class="control__5a838"><div class="container__72c38" data-full-width="false"><div class="wrapper__72c38 container__75098 md__75098 text-md/normal_cf4812" data-error="false" data-disabled="false"><input class="input__75098" placeholder="" data-mana-component="text-input" label="E-mail" id="app-change-email" aria-invalid="false" type="text" value="" name="email"></div></div></div></div>
              <div class="container__5a838" data-layout="vertical"><div class="labelContainer__5a838"><label class="text-md/medium_cf4812 label__5a838" aria-hidden="false" data-interactive="false" for="app-change-password" data-text-variant="text-md/medium" style="color: var(--text-strong);">Senha</label></div><div class="control__5a838"><div class="container__72c38" data-full-width="false"><div class="wrapper__72c38 container__75098 md__75098 text-md/normal_cf4812" data-error="false" data-disabled="false"><input class="input__75098" placeholder="" data-mana-component="text-input" label="Senha" id="app-change-password" aria-invalid="false" type="password" value="" name="password"></div></div></div></div>
            </div></div></main></div>
            <div class="bodySpacerBottom__8a031 bodySpacerBottomBorder__8a031"></div>
            <footer class="actionBar__8a031 section__8a031"><div class="actionBarTrailing__8a031 actionBarTrailingFullWidth__8a031"><div data-align="stretch" data-justify="start" data-direction="horizontal" data-wrap="true" data-full-width="true" class="stack_dbd263" style="gap: var(--space-8); padding: var(--space-0);"><button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 primary_a22cb0 hasText_a22cb0 fullWidth_a22cb0" type="button" aria-busy="false" disabled><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><span class="lineClamp1__4bd52 text-md/medium_cf4812" data-text-variant="text-md/medium">Verificar conta</span></div></div></button></div></div></footer>
          </div>
        </div>
      </div>
    </div>`;
}

function clearDialogLayer() {
  if (!activeLayer) return;
  for (const node of [...activeLayer.children]) {
    if (node.classList?.contains("root__5c9fc")) continue;
    node.remove();
  }
}

function statusErrorSvg() {
  return '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent"></circle><path fill="var(--text-feedback-critical)" fill-rule="evenodd" d="M12 23a11 11 0 1 0 0-22 11 11 0 0 0 0 22Zm1.44-15.94L13.06 14a1.06 1.06 0 0 1-2.12 0l-.38-6.94a1 1 0 0 1 1-1.06h.88a1 1 0 0 1 1 1.06Zm-.19 10.69a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" clip-rule="evenodd"></path></svg>';
}

function clearFieldError(input) {
  const field = input?.closest(".container__5a838");
  const control = field?.querySelector(".control__5a838");
  const wrapper = field?.querySelector(".wrapper__72c38");
  control?.querySelector(":scope > .helperTextContainer__5a838")?.remove();
  wrapper?.setAttribute("data-error", "false");
  input?.setAttribute("aria-invalid", "false");
  input?.removeAttribute("aria-errormessage");
}

function setFieldError(input, message, errorId) {
  if (!input) return;
  clearFieldError(input);
  const field = input.closest(".container__5a838");
  const control = field?.querySelector(".control__5a838");
  const wrapper = field?.querySelector(".wrapper__72c38");
  if (!control) return;
  wrapper?.setAttribute("data-error", "true");
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-errormessage", errorId);
  const helper = document.createElement("div");
  helper.className = "helperTextContainer__5a838";
  replaceTrustedChildren(helper, `<div class="statusMessageContainer__5a838" role="alert">${statusErrorSvg()}<div class="text-xs/normal_cf4812" id="${errorId}" data-text-variant="text-xs/normal" style="color: var(--text-feedback-critical);"></div></div>`);
  helper.querySelector(`#${errorId}`).textContent = message;
  control.appendChild(helper);
}

function openChangeEmailModal(authProvider) {
  clearDialogLayer();
  appendTrustedChildren(activeLayer, changeEmailMarkup());
  const dialog = activeLayer.querySelector("#app-change-email-dialog");
  const inputs = [...dialog.querySelectorAll("input")];
  const [emailInput, passwordInput] = inputs;
  const buttons = [...dialog.querySelectorAll("button")];
  const close = buttons[0];
  const submit = buttons.at(-1);
  let busy = false;

  const updateEnabled = () => {
    if (!submit || busy) return;
    submit.disabled = !(emailInput.value.length > 0 && passwordInput.value.length > 0);
  };
  for (const input of inputs) {
    input.addEventListener("input", () => {
      clearFieldError(input);
      updateEnabled();
    });
  }
  close?.addEventListener("click", () => openVerifyByEmailModal(authProvider), { once: true });
  submit?.addEventListener("click", async () => {
    if (busy || submit.disabled) return;
    busy = true;
    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    clearFieldError(emailInput);
    clearFieldError(passwordInput);
    try {
      const result = await authProvider.changeEmail(emailInput.value, passwordInput.value);
      if (result.error) {
        if (result.error.code === "password_mismatch") {
          setFieldError(passwordInput, "A senha não corresponde.", "app-change-password-error");
        } else if (result.error.code === "email_exists") {
          setFieldError(emailInput, "O e-mail já está registrado.", "app-change-email-error");
        } else if (result.error.code === "email_invalid") {
          setFieldError(emailInput, "Digite um endereço de e-mail válido.", "app-change-email-error");
        } else {
          setFieldError(emailInput, result.error.message || "Não foi possível alterar o e-mail.", "app-change-email-error");
        }
        return;
      }
      emit("app:email-change-success", { confirmationEmailSent: result.data?.confirmationEmailSent === true });
      openVerifyByEmailModal(authProvider, result.data?.confirmationEmailSent === true ? "E-mail enviado" : "Reenviar e-mail");
    } finally {
      busy = false;
      if (submit?.isConnected) {
        submit.setAttribute("aria-busy", "false");
        updateEnabled();
      }
    }
  });
  requestAnimationFrame(() => emailInput?.focus({ preventScroll: true }));
}

function openVerifyByEmailModal(authProvider, initialResendText = "Reenviar e-mail") {
  clearDialogLayer();
  appendTrustedChildren(activeLayer, verifyByEmailMarkup());
  const dialog = activeLayer.querySelector("#app-verify-email-dialog");
  const buttons = [...dialog.querySelectorAll("button")];
  const resend = buttons[0];
  const change = buttons[1];
  const resendLabel = resend?.querySelector("span");
  if (resendLabel) resendLabel.textContent = initialResendText;
  let busy = false;

  resend?.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    resend.disabled = true;
    resend.setAttribute("aria-busy", "true");
    try {
      const result = await authProvider.resendConfirmation();
      if (resendLabel) {
        resendLabel.textContent = result.error
          ? (result.error.code === "rate_limited" ? "Aguarde para reenviar" : "Falha ao reenviar")
          : "E-mail reenviado";
      }
      emit(result.error ? "app:verification-resend-error" : "app:verification-resend-success", { code: result.error?.code || "" });
    } finally {
      window.setTimeout(() => {
        if (!resend?.isConnected) return;
        if (resendLabel) resendLabel.textContent = "Reenviar e-mail";
        resend.disabled = false;
        resend.setAttribute("aria-busy", "false");
        busy = false;
      }, 1800);
    }
  });
  change?.addEventListener("click", () => openChangeEmailModal(authProvider), { once: true });
  requestAnimationFrame(() => dialog?.focus({ preventScroll: true }));
}

export function showVerificationRequired(authProvider) {
  activeAuthProvider = authProvider;
  const layer = verificationLayer();
  replaceTrustedChildren(layer, verificationRequiredMarkup());
  OverlayManager.claim({ id: "verification-required", type: "modal", close: closeVerificationFlow });
  const buttons = [...layer.querySelectorAll(".verification_dede4b button")];
  const verifyButton = buttons[0];
  const links = [...layer.querySelectorAll(".verification_dede4b a")];
  const logout = links.at(-1);
  verifyButton?.addEventListener("click", () => openVerifyByEmailModal(authProvider), { once: true });
  logout?.addEventListener("click", async (event) => {
    event.preventDefault();
    const result = await authProvider.logout();
    if (!result.error) location.replace(appUrl("login.html"));
  }, { once: true });
  emit("app:verification-required-opened");
}

export function wireVerificationNotice(authProvider, session) {
  const notice = document.querySelector(".notice__6e2b9");
  if (!notice) return;
  const button = notice.querySelector("button.button__6e2b9");
  if (session?.user?.emailConfirmed === true || session?.role === "user") {
    notice.remove();
    return;
  }
  button?.addEventListener("click", (event) => {
    event.preventDefault();
    showVerificationRequired(authProvider);
  });
}

export { openVerifyByEmailModal };
