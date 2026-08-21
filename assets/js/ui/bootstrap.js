import { clearInitialFocus, ensureAuthProvider, wireInputFocusStates, wireNavigation } from "./runtime.js";
import { State } from "./state.js";

let booted = false;

function prewarmHumanVerification() {
  void import("./captcha.js")
    .then(({ prewarmCaptcha }) => prewarmCaptcha())
    .catch(() => {});
}

async function bootLogin() {
  if (new URL(location.href).searchParams.has("code")) {
    const authProvider = await ensureAuthProvider();
    const session = await authProvider.session();
    if (session?.authenticated) {
      location.replace("channels.html");
      return;
    }
  }
  const { wireForgotPassword, wireLoginForm, wirePasskeyLogin } = await import("./login.js");
  const loginErrors = wireLoginForm();
  wireForgotPassword(loginErrors);
  wirePasskeyLogin();
  prewarmHumanVerification();
}

async function bootRegister() {
  const [validationModule, dateModule, formModule] = await Promise.all([
    import("./register-validation.js"),
    import("./date-menu.js"),
    import("./register-form.js"),
  ]);

  validationModule.wireRegisterAnimatedFieldHints();
  validationModule.wireRegisterEmailAccess();
  const registerValidation = validationModule.wireRegisterValidation();
  validationModule.wireMarketingCheckbox();
  const dateState = dateModule.wireDateOfBirth();
  formModule.wireRegisterForm(dateState, registerValidation);
  prewarmHumanVerification();
}

async function bootChannels() {
  const { wireChannelsPage } = await import("./channels.js");
  await wireChannelsPage();
}

async function start() {
  if (booted) return;
  booted = true;

  // Only global shell behavior is initialized here. Page-specific features are
  // dynamically imported for the current route, preventing registration-only
  // modules (date menus, menu catalog, sliding highlight, etc.) from being
  // downloaded on the login page.
  wireNavigation();
  wireInputFocusStates();

  try {
    if (State.page === "login") await bootLogin();
    else if (State.page === "register") await bootRegister();
    else if (State.page === "channels") await bootChannels();
  } catch (error) {
    console.error("Falha ao inicializar a rota atual.", error);
    document.dispatchEvent(new CustomEvent("app:route-bootstrap-error", {
      detail: { page: State.page, error },
    }));
  }

  requestAnimationFrame(clearInitialFocus);
  window.addEventListener("pageshow", () => requestAnimationFrame(clearInitialFocus));
}

export function boot() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}
