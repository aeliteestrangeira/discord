import { State } from "./state.js";
import { ensureAuthProvider } from "./runtime.js";
import { replaceTrustedChildren } from "./dom.js";

function wireRegisterAnimatedFieldHints() {
  if (State.page !== "register") return;

  // Both helper rows use the same captured open/closed geometry. Keeping the
  // behavior in one routine avoids duplicating animation logic while
  // preserving the original DOM and CSS.
  const closed = Object.freeze({ height: "0px", paddingBottom: "0px", marginTop: "0px", opacity: "0" });
  const open = Object.freeze({ height: "18px", paddingBottom: "20px", marginTop: "-12px", opacity: "1" });

  function wire(inputName, message) {
    const input = document.querySelector(`input[name="${inputName}"]`);
    const field = input?.closest(".marginBottom20_fd297e");
    const hint = field?.nextElementSibling;
    const inner = hint?.firstElementChild;
    const text = inner?.querySelector('[data-text-variant="text-sm/normal"]');
    if (!input || !hint || !inner || !text) return;

    let outerAnimation = null;
    let innerAnimation = null;

    text.textContent = message;

    function commit(target) {
      hint.style.overflow = "hidden";
      hint.style.height = target.height;
      hint.style.paddingBottom = target.paddingBottom;
      hint.style.marginTop = target.marginTop;
      hint.style.pointerEvents = "none";
      inner.style.opacity = target.opacity;
    }

    function animateTo(target) {
      const outerStyle = getComputedStyle(hint);
      const innerStyle = getComputedStyle(inner);
      const fromOuter = {
        height: outerStyle.height,
        paddingBottom: outerStyle.paddingBottom,
        marginTop: outerStyle.marginTop
      };
      const toOuter = {
        height: target.height,
        paddingBottom: target.paddingBottom,
        marginTop: target.marginTop
      };
      const fromInner = { opacity: innerStyle.opacity };
      const toInner = { opacity: target.opacity };

      outerAnimation?.cancel();
      innerAnimation?.cancel();

      if (typeof hint.animate !== "function") {
        commit(target);
        return;
      }

      outerAnimation = hint.animate([fromOuter, toOuter], {
        duration: 180,
        easing: "cubic-bezier(0.2, 0, 0, 1)",
        fill: "none"
      });
      innerAnimation = inner.animate([fromInner, toInner], {
        duration: 150,
        easing: "ease-out",
        fill: "none"
      });

      outerAnimation.addEventListener("finish", () => commit(target), { once: true });
      innerAnimation.addEventListener("finish", () => { inner.style.opacity = target.opacity; }, { once: true });
    }

    // The helper remains collapsed until this specific field receives real
    // focus, then reverses the same animation when focus leaves it.
    commit(closed);
    input.addEventListener("focus", () => animateTo(open));
    input.addEventListener("blur", () => animateTo(closed));
  }

  wire("global_name", "É assim que as pessoas veem você.");
}

function wireRegisterEmailAccess() {
  if (State.page !== "register") return;

  const emailInput = document.querySelector('input[name="email"]');
  const field = emailInput?.closest('.marginBottom20_fd297e');
  const heading = document.querySelector('.title__921c5');
  const logo = document.querySelector('.discordLogo__921c5');
  if (!emailInput || !field) return;

  const focusEmail = () => {
    requestAnimationFrame(() => {
      if (document.activeElement !== emailInput) {
        emailInput.focus({ preventScroll: true });
      }
    });
  };

  // Defensive fix for zoom/layout edge cases: keep decorative siblings from
  // intercepting clicks and keep the first field above nearby overlap.
  field.style.position = 'relative';
  field.style.zIndex = '2';
  field.style.pointerEvents = 'auto';
  if (heading) heading.style.pointerEvents = 'none';
  if (logo) logo.style.pointerEvents = 'none';

  for (const target of [field, field.querySelector('.container__5a838'), field.querySelector('.control__5a838'), field.querySelector('.container__72c38'), field.querySelector('.wrapper__72c38')]) {
    if (!target) continue;
    target.style.position = target.style.position || 'relative';
    target.style.pointerEvents = 'auto';
    target.addEventListener('mousedown', (event) => {
      if (event.target === emailInput) return;
      focusEmail();
    });
    target.addEventListener('click', (event) => {
      if (event.target === emailInput) return;
      focusEmail();
    });
  }
}

function wireRegisterValidation() {
  if (State.page !== "register") return null;

  const form = document.querySelector("form");
  const email = form?.elements.namedItem("email");
  const globalName = form?.elements.namedItem("global_name");
  const username = form?.elements.namedItem("username");
  if (!form || !email || !globalName || !username) return null;

  const errorSvg = '<svg aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="none" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="transparent" class=""></circle><path fill="var(--text-feedback-critical)" fill-rule="evenodd" d="M12 23a11 11 0 1 0 0-22 11 11 0 0 0 0 22Zm1.44-15.94L13.06 14a1.06 1.06 0 0 1-2.12 0l-.38-6.94a1 1 0 0 1 1-1.06h.88a1 1 0 0 1 1 1.06Zm-.19 10.69a1.25 1.25 0 1 1-2.5 0 1.25 1.25 0 0 1 2.5 0Z" clip-rule="evenodd" class=""></path></svg>';

  function fieldState(input, id) {
    const field = input.closest(".container__5a838");
    const control = field?.querySelector(".control__5a838");
    const visual = input.closest(".wrapper__72c38.container__75098");
    if (!field || !control || !visual) return null;

    function clearRequired() {
      visual.setAttribute("data-error", "false");
      input.setAttribute("aria-invalid", "false");
      input.removeAttribute("aria-errormessage");
      control.querySelector(`[data-app-register-required="${id}"]`)?.remove();
    }

    function showRequired(message = "Obrigatório") {
      clearRequired();
      visual.setAttribute("data-error", "true");
      input.setAttribute("aria-invalid", "true");
      input.setAttribute("aria-errormessage", id);
      const helper = document.createElement("div");
      helper.className = "helperTextContainer__5a838";
      helper.dataset.appRegisterRequired = id;
      const status = document.createElement("div");
      status.className = "statusMessageContainer__5a838";
      status.setAttribute("role", "alert");
      replaceTrustedChildren(status, `${errorSvg}<div class="text-xs/normal_cf4812" id="${id}" data-text-variant="text-xs/normal" style="color: var(--text-feedback-critical);"></div>`);
      status.querySelector(`#${id}`).textContent = message;
      helper.appendChild(status);
      control.appendChild(helper);
    }

    return { clearRequired, showRequired };
  }

  const emailState = fieldState(email, "app-register-email-required");
  const usernameRequiredState = fieldState(username, "app-register-username-required");
  let emailHadValue = Boolean(email.value.trim());
  let usernameHadValue = Boolean(username.value.trim());

  email.addEventListener("input", () => {
    if (email.value.trim()) {
      emailHadValue = true;
      emailState?.clearRequired();
    } else if (emailHadValue) {
      emailState?.showRequired();
    }
  });

  const usernameField = username.closest(".marginBottom20_fd297e");
  const hint = usernameField?.nextElementSibling;
  const hintInner = hint?.firstElementChild;
  const hintText = hintInner?.querySelector('[data-text-variant="text-sm/normal"]');
  if (!usernameField || !hint || !hintInner || !hintText) {
    return { emailState, usernameState: null };
  }

  const hintDefault = "Use apenas números, letras, sublinhados _ ou pontos.";
  let hintOuterAnimation = null;
  let hintInnerAnimation = null;
  let availabilityTimer = null;
  let suggestionTimer = null;
  let suggestionFallbackTimer = null;
  let requestGeneration = 0;
  let suggestionGeneration = 0;
  let usernameStatus = "idle";
  let lastChecked = "";
  let lastAvailable = null;
  let currentSuggestion = null;
  let currentSuggestionFor = "";
  let currentSuggestionConfirmedAt = 0;
  let suggestionInFlightFor = "";
  let suggestionInFlight = null;

  function commitHint(height, opacity) {
    hint.style.overflow = "hidden";
    hint.style.height = `${height}px`;
    hint.style.paddingBottom = height > 0 ? "20px" : "0px";
    hint.style.marginTop = height > 0 ? "-12px" : "0px";
    hintInner.style.opacity = String(opacity);
  }

  function animateHint(height) {
    const targetOpacity = height > 0 ? 1 : 0;
    const outerStyle = getComputedStyle(hint);
    const innerStyle = getComputedStyle(hintInner);
    const fromOuter = { height: outerStyle.height, paddingBottom: outerStyle.paddingBottom, marginTop: outerStyle.marginTop };
    const toOuter = { height: `${height}px`, paddingBottom: height > 0 ? "20px" : "0px", marginTop: height > 0 ? "-12px" : "0px" };
    const fromInner = { opacity: innerStyle.opacity };
    const toInner = { opacity: String(targetOpacity) };

    hintOuterAnimation?.cancel();
    hintInnerAnimation?.cancel();
    if (typeof hint.animate !== "function") {
      commitHint(height, targetOpacity);
      return;
    }
    hintOuterAnimation = hint.animate([fromOuter, toOuter], { duration: 180, easing: "cubic-bezier(0.2, 0, 0, 1)", fill: "none" });
    hintInnerAnimation = hintInner.animate([fromInner, toInner], { duration: 150, easing: "ease-out", fill: "none" });
    hintOuterAnimation.addEventListener("finish", () => commitHint(height, targetOpacity), { once: true });
    hintInnerAnimation.addEventListener("finish", () => { hintInner.style.opacity = String(targetOpacity); }, { once: true });
  }

  function resetHintClass() {
    hintText.className = "text-sm/normal_cf4812";
    hintText.style.color = "var(--text-default)";
    hintText.replaceChildren();
    hint.style.pointerEvents = "none";
  }

  function showDefaultHint() {
    usernameStatus = "hint";
    resetHintClass();
    hintText.textContent = hintDefault;
    animateHint(18);
  }

  function showNegative(message, height = 18) {
    usernameStatus = "negative";
    resetHintClass();
    hintText.className = "defaultColor__4bd52 text-sm/normal_cf4812 messageNegative_d332d2";
    hintText.style.removeProperty("color");
    hintText.textContent = message;
    animateHint(height);
  }

  function showPositive({ visible = document.activeElement === username } = {}) {
    usernameStatus = "available";
    resetHintClass();
    hintText.className = "defaultColor__4bd52 text-sm/normal_cf4812 messagePositive_d332d2";
    hintText.style.removeProperty("color");
    hintText.textContent = "Nome de usuário disponível. Ótimo!";
    animateHint(visible ? 18 : 0);
  }

  function showSuggestion(suggestion) {
    if (!suggestion || username.value.trim()) return;
    currentSuggestion = suggestion;
    usernameStatus = "suggestion";
    resetHintClass();
    hint.style.pointerEvents = "auto";
    hintText.appendChild(document.createTextNode("Aqui está uma sugestão: "));
    const anchor = document.createElement("a");
    anchor.className = "anchor_edefb8 anchorUnderlineOnHover_edefb8";
    anchor.setAttribute("role", "link");
    anchor.setAttribute("tabindex", "0");
    anchor.textContent = suggestion;
    let suggestionAccepted = false;
    const acceptSuggestion = (event) => {
      event?.preventDefault();
      event?.stopPropagation();
      if (suggestionAccepted) return;
      suggestionAccepted = true;

      // Accept on pointer-down, before Username can blur and collapse the
      // animated suggestion row under the pointer. This prevents the original
      // click target from disappearing before the browser emits `click`.
      const suggestionWasFresh = currentSuggestion === suggestion
        && currentSuggestionFor === globalName.value.trim()
        && (Date.now() - currentSuggestionConfirmedAt) < 15000;
      clearTimeout(availabilityTimer);
      clearTimeout(suggestionFallbackTimer);
      username.value = suggestion;
      usernameHadValue = true;
      usernameRequiredState?.clearRequired();
      username.focus({ preventScroll: true });
      username.dispatchEvent(new Event("input", { bubbles: true }));
      clearTimeout(availabilityTimer);

      // A suggestion returned by /username/suggest was already checked against
      // the database. For the normal immediate-click path, reuse that fresh
      // result so the positive state appears in the same frame instead of
      // briefly falling back to the generic guidance and doing a second round-trip.
      // Registration still rechecks server-side and the database uniqueness
      // constraint remains the final race-condition guard.
      if (suggestionWasFresh) {
        lastChecked = suggestion;
        lastAvailable = true;
        currentSuggestion = null;
        currentSuggestionFor = "";
        currentSuggestionConfirmedAt = 0;
        showPositive({ visible: true });
      } else {
        void checkAvailability(username.value.trim(), { immediate: true });
      }
    };
    anchor.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      acceptSuggestion(event);
    });
    anchor.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (!suggestionAccepted) acceptSuggestion(event);
    });
    anchor.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") acceptSuggestion(event);
    });
    hintText.appendChild(anchor);
    animateHint(18);
  }

  function closeHintIfIdle() {
    if (["available", "negative", "suggestion"].includes(usernameStatus)) return;
    usernameStatus = "idle";
    animateHint(0);
  }

  function formatState(value) {
    if (value.length < 2 || value.length > 32) return "length";
    if (!/^[a-z0-9_.]+$/.test(value)) return "characters";
    if (/\.\./.test(value)) return "repeating-dots";
    return "valid";
  }

  async function checkAvailability(value, { immediate = false } = {}) {
    const normalized = value.trim();
    const format = formatState(normalized);
    if (format === "length") {
      lastChecked = normalized;
      lastAvailable = false;
      showNegative("Deve ter entre 2 e 32 caracteres.");
      return false;
    }
    if (format === "characters") {
      lastChecked = normalized;
      lastAvailable = false;
      showNegative("Use apenas números, letras, sublinhados _ ou pontos.");
      return false;
    }
    if (format === "repeating-dots") {
      lastChecked = normalized;
      lastAvailable = false;
      showNegative("Nome de usuário não pode conter pontos repetidos.");
      return false;
    }

    const generation = ++requestGeneration;
    if (!immediate) showDefaultHint();
    try {
      const authProvider = await ensureAuthProvider();
      const result = await authProvider.checkUsername(normalized);
      if (generation !== requestGeneration || username.value.trim() !== normalized) return null;
      lastChecked = normalized;
      lastAvailable = result.available;
      if (result.available === true) {
        showPositive();
        return true;
      }
      if (result.available === false) {
        showNegative("Nome de usuário indisponível. Tente adicionar números, letras, sublinhados _ ou pontos.", 36);
        return false;
      }
      usernameStatus = "lookup-error";
      showNegative("Não foi possível verificar o nome de usuário agora.", 18);
      return null;
    } catch (_) {
      if (generation !== requestGeneration) return null;
      usernameStatus = "lookup-error";
      showNegative("Não foi possível verificar o nome de usuário agora.", 18);
      return null;
    }
  }

  async function requestSuggestion() {
    const displayValue = globalName.value.trim();
    if (!displayValue || username.value.trim()) return null;
    if (currentSuggestion && currentSuggestionFor === displayValue) {
      clearTimeout(suggestionFallbackTimer);
      if (document.activeElement === username) showSuggestion(currentSuggestion);
      return currentSuggestion;
    }
    if (suggestionInFlight && suggestionInFlightFor === displayValue) {
      return suggestionInFlight;
    }

    const generation = ++suggestionGeneration;
    suggestionInFlightFor = displayValue;
    suggestionInFlight = (async () => {
      try {
        const authProvider = await ensureAuthProvider();
        const result = await authProvider.suggestUsername(displayValue);
        if (generation !== suggestionGeneration || username.value.trim() || globalName.value.trim() !== displayValue) return null;
        if (result.suggestion) {
          currentSuggestion = result.suggestion;
          currentSuggestionFor = displayValue;
          currentSuggestionConfirmedAt = Date.now();
          clearTimeout(suggestionFallbackTimer);
          // The suggestion is contextual to Username. Preload it while the user
          // edits Display Name, but do not render it until Username receives focus.
          if (document.activeElement === username) showSuggestion(result.suggestion);
          return result.suggestion;
        }
      } catch (_) {
        // Suggestions are assistive only; absence never weakens validation.
      }
      return null;
    })();

    try {
      return await suggestionInFlight;
    } finally {
      if (suggestionInFlightFor === displayValue) {
        suggestionInFlightFor = "";
        suggestionInFlight = null;
      }
    }
  }

  function scheduleSuggestion(delay = 180) {
    clearTimeout(suggestionTimer);
    suggestionGeneration += 1;
    if (!globalName.value.trim() || username.value.trim()) return;
    // Preload silently while Display Name is being edited. The focus path below
    // bypasses this debounce and starts the database-backed lookup immediately.
    suggestionTimer = window.setTimeout(() => void requestSuggestion(), delay);
  }

  username.addEventListener("focus", () => {
    const value = username.value.trim();
    if (!value) {
      clearTimeout(suggestionFallbackTimer);
      if (currentSuggestion && currentSuggestionFor === globalName.value.trim()) {
        showSuggestion(currentSuggestion);
      } else if (globalName.value.trim()) {
        // Do not restart the debounce when Username receives focus. Start the
        // server/database lookup now. A short fallback delay prevents the generic
        // guidance from flashing when the optimized suggestion response arrives
        // quickly; if the network is slower, the normal hint remains available.
        clearTimeout(suggestionTimer);
        animateHint(0);
        suggestionFallbackTimer = window.setTimeout(() => {
          if (document.activeElement === username
              && !username.value.trim()
              && !(currentSuggestion && currentSuggestionFor === globalName.value.trim())) {
            showDefaultHint();
          }
        }, 120);
        void requestSuggestion();
      } else {
        showDefaultHint();
      }
      return;
    }
    if (lastChecked === value && lastAvailable === true) {
      showPositive({ visible: true });
    }
  });

  username.addEventListener("blur", () => {
    clearTimeout(suggestionFallbackTimer);
    if (usernameStatus === "available" || usernameStatus === "suggestion" || usernameStatus === "hint") {
      // Positive state, suggestion and neutral guidance are contextual to the
      // Username focus. Validation errors remain visible, but these helpers close
      // when focus moves to another field or outside the form.
      animateHint(0);
      return;
    }
    if (!username.value.trim() && !globalName.value.trim()) closeHintIfIdle();
  });

  username.addEventListener("input", () => {
    clearTimeout(availabilityTimer);
    requestGeneration += 1;

    // Username is canonical lowercase. Convert immediately even when Caps Lock
    // or Shift produced uppercase characters, while preserving the caret/selection.
    const rawUsername = username.value;
    const canonicalUsername = rawUsername.toLowerCase();
    if (canonicalUsername !== rawUsername) {
      const selectionStart = username.selectionStart;
      const selectionEnd = username.selectionEnd;
      username.value = canonicalUsername;
      if (selectionStart !== null && selectionEnd !== null) {
        username.setSelectionRange(selectionStart, selectionEnd);
      }
    }

    const value = username.value.trim();
    if (!value) {
      lastChecked = "";
      lastAvailable = null;
      // Required is an interaction error: show it only after Username itself had
      // content and was cleared. A Display Name by itself must not trigger it.
      if (usernameHadValue) usernameRequiredState?.showRequired();
      else usernameRequiredState?.clearRequired();
      if (globalName.value.trim()) {
        scheduleSuggestion();
        if (document.activeElement === username && currentSuggestion && currentSuggestionFor === globalName.value.trim()) showSuggestion(currentSuggestion);
        else if (document.activeElement === username) showDefaultHint();
        else animateHint(0);
      } else if (document.activeElement === username) {
        showDefaultHint();
      } else {
        animateHint(0);
      }
      return;
    }

    usernameHadValue = true;
    currentSuggestion = null;
    suggestionGeneration += 1;
    usernameRequiredState?.clearRequired();
    const state = formatState(value);
    if (state === "length") {
      lastChecked = value;
      lastAvailable = false;
      showNegative("Deve ter entre 2 e 32 caracteres.");
      return;
    }
    if (state === "characters") {
      lastChecked = value;
      lastAvailable = false;
      showNegative("Use apenas números, letras, sublinhados _ ou pontos.");
      return;
    }
    if (state === "repeating-dots") {
      lastChecked = value;
      lastAvailable = false;
      showNegative("Nome de usuário não pode conter pontos repetidos.");
      return;
    }
    showDefaultHint();
    availabilityTimer = window.setTimeout(() => void checkAvailability(value), 320);
  });

  globalName.addEventListener("input", () => {
    if (!username.value.trim()) {
      // Any Display Name edit invalidates the previously cached candidate.
      currentSuggestion = null;
      currentSuggestionFor = "";
      currentSuggestionConfirmedAt = 0;
      if (globalName.value.trim()) {
        // Preload a candidate silently. Do not show Required or the suggestion
        // while focus remains in Display Name (or any field other than Username).
        if (!usernameHadValue) usernameRequiredState?.clearRequired();
        scheduleSuggestion();
        if (document.activeElement !== username) animateHint(0);
      } else {
        suggestionGeneration += 1;
        if (!usernameHadValue) usernameRequiredState?.clearRequired();
        if (document.activeElement === username) showDefaultHint();
        else animateHint(0);
      }
    }
  });

  async function validateUsernameForSubmit() {
    clearTimeout(availabilityTimer);
    const value = username.value.trim();
    if (!value) {
      usernameRequiredState?.showRequired();
      if (globalName.value.trim()) scheduleSuggestion();
      username.focus({ preventScroll: true });
      return false;
    }
    const format = formatState(value);
    if (format === "length") {
      showNegative("Deve ter entre 2 e 32 caracteres.");
      username.focus({ preventScroll: true });
      return false;
    }
    if (format === "characters") {
      showNegative("Use apenas números, letras, sublinhados _ ou pontos.");
      username.focus({ preventScroll: true });
      return false;
    }
    if (format === "repeating-dots") {
      showNegative("Nome de usuário não pode conter pontos repetidos.");
      username.focus({ preventScroll: true });
      return false;
    }
    if (lastChecked === value && lastAvailable === true) return true;
    const available = await checkAvailability(value, { immediate: true });
    if (available !== true) username.focus({ preventScroll: true });
    return available === true;
  }

  function showUnavailable() {
    usernameRequiredState?.clearRequired();
    lastChecked = username.value.trim();
    lastAvailable = false;
    showNegative("Nome de usuário indisponível. Tente adicionar números, letras, sublinhados _ ou pontos.", 36);
    username.focus({ preventScroll: true });
  }

  return {
    emailState,
    usernameState: {
      validateForSubmit: validateUsernameForSubmit,
      showUnavailable,
    },
    validateEmailForSubmit() {
      if (!email.value.trim()) {
        emailState?.showRequired();
        email.focus({ preventScroll: true });
        return false;
      }
      emailState?.clearRequired();
      return true;
    }
  };
}

function wireMarketingCheckbox() {
  if (State.page !== "register") return;

  const checkbox = document.querySelector('input[type="checkbox"]');
  const option = checkbox?.closest(".checkboxOption__714a9");
  if (!checkbox || !option) return;

  function sync() {
    State.marketingOptIn = checkbox.checked;
    if (checkbox.checked) option.setAttribute("data-selected", "true");
    else option.removeAttribute("data-selected");
    checkbox.setAttribute("aria-checked", String(checkbox.checked));
  }

  option.addEventListener("click", (event) => {
    if (event.target === checkbox) return;
    event.preventDefault();
    checkbox.checked = !checkbox.checked;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    checkbox.focus({ preventScroll: true });
  });

  checkbox.addEventListener("change", sync);
  sync();
}


export { wireRegisterAnimatedFieldHints, wireRegisterEmailAccess, wireRegisterValidation, wireMarketingCheckbox };
