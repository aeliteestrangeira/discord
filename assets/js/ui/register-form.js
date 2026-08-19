import { State } from "./state.js";
import { emit, ensureAuthProvider, navigate, setBusy } from "./runtime.js";

function registrationProfile(form) {
  const globalName = form.elements.namedItem("global_name")?.value?.trim() || "";
  const username = form.elements.namedItem("username")?.value?.trim() || "";
  const metadata = {};
  if (globalName) metadata.global_name = globalName;
  if (username) metadata.username = username;
  if (State.dateOfBirth) {
    metadata.date_of_birth = `${State.dateOfBirth.year}-${State.dateOfBirth.month}-${State.dateOfBirth.day}`;
  }
  return metadata;
}

function wireRegisterForm(dateState, validationState) {
  if (State.page !== "register") return;
  const form = dateState?.form || document.querySelector("form");
  if (!form) return;
  const passwordInput = form.elements.namedItem("password");
  passwordInput?.addEventListener("input", () => passwordInput.setCustomValidity(""));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const emailValid = validationState?.validateEmailForSubmit ? validationState.validateEmailForSubmit() : true;
    const usernameValid = validationState?.usernameState?.validateForSubmit
      ? await validationState.usernameState.validateForSubmit()
      : true;
    const dobValid = dateState?.validateForSubmit ? dateState.validateForSubmit() : Boolean(State.dateOfBirth);
    if (!emailValid || !usernameValid || !dobValid) {
      State.status = "invalid";
      return;
    }

    const nativeInputsValid = form.checkValidity();
    if (!nativeInputsValid) {
      State.status = "invalid";
      form.reportValidity();
      return;
    }

    const email = form.elements.namedItem("email")?.value?.trim() || "";
    const passwordInput = form.elements.namedItem("password");
    const password = passwordInput?.value || "";
    if (password.length < 16) {
      State.status = "invalid";
      passwordInput?.setCustomValidity("Use uma senha exclusiva com pelo menos 16 caracteres.");
      passwordInput?.reportValidity();
      passwordInput?.focus({ preventScroll: true });
      return;
    }
    passwordInput?.setCustomValidity("");
    State.status = "authenticating";
    setBusy(form, true);

    try {
      const { requestCaptchaToken } = await import("./captcha.js");
      const hcaptchaToken = await requestCaptchaToken();
      const authProvider = await ensureAuthProvider();
      const result = await authProvider.signUp(email, password, registrationProfile(form), State.marketingOptIn, hcaptchaToken);
      if (!result.configured) {
        State.status = "ready-for-auth-provider";
        emit("app:auth-unconfigured", { type: "register" });
        return;
      }
      if (result.error) {
        State.status = "auth-error";
        if (result.error.code === "username_unavailable") {
          validationState?.usernameState?.showUnavailable?.();
        }
        emit("app:auth-error", { type: "register", error: result.error });
        return;
      }
      State.status = "authenticated-or-confirmation-pending";
      emit("app:auth-success", { type: "register", data: result.data, profile: registrationProfile(form), marketingOptIn: State.marketingOptIn });
      navigate(result.data?.redirect || "/channels/@me");
    } catch (error) {
      if (error?.name === "AbortError") {
        State.status = "idle";
        emit("app:captcha-cancelled", { type: "register" });
      } else {
        State.status = "auth-error";
        emit("app:auth-error", { type: "register", error });
      }
    } finally {
      setBusy(form, false);
    }
  });
}


export { registrationProfile, wireRegisterForm };
