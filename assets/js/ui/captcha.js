import { OverlayManager } from "./overlay-manager.js";
import { replaceTrustedChildren } from "./dom.js";

let captchaConfigPromise;
let captchaCssPromise;
let hcaptchaApiPromise;
const HCAPTCHA_ONLOAD_CALLBACK = "__discordHCaptchaReady";

function ensureCaptchaCss() {
  const existing = document.querySelector('link[data-app-captcha-css="true"]');
  if (existing?.sheet) return Promise.resolve(existing);
  if (captchaCssPromise) return captchaCssPromise;

  captchaCssPromise = new Promise((resolve, reject) => {
    const link = existing || document.createElement("link");
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      resolve(link);
    };
    const fail = () => {
      if (settled) return;
      settled = true;
      reject(new Error("Falha ao carregar o estilo da verificacao humana."));
    };

    link.addEventListener("load", finish, { once: true });
    link.addEventListener("error", fail, { once: true });

    if (!existing) {
      link.rel = "stylesheet";
      link.href = new URL("../captcha.css", import.meta.url).href;
      link.dataset.appCaptchaCss = "true";
      document.head.appendChild(link);
    }
    if (link.sheet) finish();
  }).catch((error) => {
    captchaCssPromise = undefined;
    throw error;
  });

  return captchaCssPromise;
}

async function getCaptchaConfig() {
  if (!captchaConfigPromise) {
    const isCloud = location.origin === "https://aeliteestrangeira.github.io" &&
      location.pathname.toLowerCase().startsWith("/discord/");
    if (isCloud) {
      captchaConfigPromise = new Promise((resolve, reject) => {
        if (window.AppCloudRuntime?.captchaConfig) {
          window.AppCloudRuntime.captchaConfig().then(resolve, reject);
          return;
        }
        const existing = document.querySelector('script[data-app-cloud-runtime="true"]');
        const script = existing || document.createElement("script");
        const loaded = () => {
          if (!window.AppCloudRuntime?.captchaConfig) {
            reject(new Error("Cloud runtime indisponível."));
            return;
          }
          window.AppCloudRuntime.captchaConfig().then(resolve, reject);
        };
        script.addEventListener("load", loaded, { once: true });
        script.addEventListener("error", () => reject(new Error("Falha ao carregar cloud runtime.")), { once: true });
        if (!existing) {
          script.src = new URL("../cloud-runtime.js", import.meta.url).href;
          script.async = true;
          script.dataset.appCloudRuntime = "true";
          document.head.appendChild(script);
        } else if (window.AppCloudRuntime?.captchaConfig) {
          loaded();
        }
      }).catch((error) => {
        captchaConfigPromise = undefined;
        throw error;
      });
      return captchaConfigPromise;
    }
    captchaConfigPromise = fetch("/api/security/hcaptcha", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" }
    }).then(async (response) => {
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error("Falha ao carregar a verificacao humana.");
      return body;
    }).catch((error) => {
      captchaConfigPromise = undefined;
      throw error;
    });
  }
  return captchaConfigPromise;
}

function ensureHCaptchaApi() {
  if (window.hcaptcha?.render) return Promise.resolve(window.hcaptcha);
  if (hcaptchaApiPromise) return hcaptchaApiPromise;

  hcaptchaApiPromise = new Promise((resolve, reject) => {
    let settled = false;
    let timer = null;
    let script = document.querySelector('script[data-app-hcaptcha="true"]');

    const clearReadyCallback = () => {
      if (window[HCAPTCHA_ONLOAD_CALLBACK] === ready) {
        try { delete window[HCAPTCHA_ONLOAD_CALLBACK]; } catch (_) {
          window[HCAPTCHA_ONLOAD_CALLBACK] = undefined;
        }
      }
    };
    const succeed = () => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      clearReadyCallback();
      if (!window.hcaptcha?.render) {
        reject(new Error("hCaptcha indisponivel apos inicializacao."));
        return;
      }
      resolve(window.hcaptcha);
    };
    const fail = () => {
      if (settled) return;
      settled = true;
      if (timer) window.clearTimeout(timer);
      clearReadyCallback();
      reject(new Error("Falha ao carregar hCaptcha."));
    };
    const ready = () => succeed();

    // For explicit rendering, readiness is the SDK onload callback. A DOM
    // script-load event alone is not sufficient evidence that render is ready.
    window[HCAPTCHA_ONLOAD_CALLBACK] = ready;

    const sdkHost = String(location.hostname || "").trim().toLowerCase();
    if (!script) {
      if (!sdkHost) {
        fail();
        return;
      }
      console.info(`[hcaptcha] sdk-load host=${sdkHost}`);
      script = document.createElement("script");
      script.src = `https://js.hcaptcha.com/1/api.js?hl=pt-BR&render=explicit&recaptchacompat=off&host=${encodeURIComponent(sdkHost)}&onload=${encodeURIComponent(HCAPTCHA_ONLOAD_CALLBACK)}`;
      script.async = true;
      script.defer = true;
      script.dataset.appHcaptcha = "true";
      document.head.appendChild(script);
    }

    script.addEventListener("error", fail, { once: true });
    timer = window.setTimeout(fail, 20000);
  }).catch((error) => {
    hcaptchaApiPromise = undefined;
    document.querySelector('script[data-app-hcaptcha="true"]')?.remove();
    throw error;
  });

  return hcaptchaApiPromise;
}

async function prewarmCaptcha() {
  try {
    const config = await getCaptchaConfig();
    if (!config?.configured || !config?.sitekey) {
      return { ok: false, reason: "not-configured" };
    }
    await ensureHCaptchaApi();
    return { ok: true };
  } catch (error) {
    return { ok: false, reason: error?.message || "prewarm-failed" };
  }
}

function captchaLayer() {
  const layers = [...document.querySelectorAll(".layerContainer__59d0d")];
  let layer = layers.reverse().find((candidate) => candidate.childElementCount === 0);
  if (!layer) {
    layer = document.createElement("div");
    layer.className = "layerContainer__59d0d";
    document.body.appendChild(layer);
  }
  return layer;
}

function captchaModalMarkup() {
  return `
    <div role="none" class="scrim__40128" style="opacity: 1;"></div>
    <div class="layer_bc663c">
      <div id="app-hcaptcha-dialog" aria-label="Espere! Você é humano?" data-dialog="modal" role="dialog" aria-modal="true" tabindex="-1">
        <span class="hiddenVisually_b18fe2"><div data-live-announcer="true" style="border:0;clip:rect(0px,0px,0px,0px);clip-path:inset(50%);height:1px;margin:-1px;overflow:hidden;padding:0;position:absolute;width:1px;white-space:nowrap;"><div role="log" aria-live="assertive" aria-relevant="additions"></div><div role="log" aria-live="polite" aria-relevant="additions"></div></div></span>
        <div class="outerContainer__8a031 fullScreenOnMobile__8a031">
          <div data-mana-component="modal" class="container__8a031 size-sm__8a031 padding-size-lg__8a031" style="opacity:1;transform:scale(1);">
            <div class="container_a62383 blue_a62383 headerGradient__8a031" style="--custom-gradient-offset-bottom:0%;">
              <header class="section__8a031 header__8a031 headerCentered__8a031">
                <div data-align="stretch" data-justify="start" data-direction="vertical" data-wrap="false" data-full-width="true" class="stack_dbd263" style="gap:var(--space-8);padding:var(--space-0);">
                  <div class="headerLayout__8a031">
                    <div class="headerLeading__8a031 headerLeadingAbsolute__8a031"></div>
                    <div class="headerLeadingSpacer__8a031" style="height:38px;width:50px;"></div>
                    <div class="headerMain__8a031"><div class="headerGraphic__8a031"><div class="headerGraphicContainer__8a031"><div class="container__8ef77 aspect-ratio-16/9__8ef77"><img class="image__8ef77" alt="" draggable="false" src="${new URL("../assets/a1c385fb82c39bab.svg", import.meta.url).href}"></div></div></div></div>
                    <div class="headerTrailingSpacer__8a031" style="height:38px;width:50px;"></div>
                    <div class="headerTrailing__8a031 headerTrailingAbsolute__8a031">
                      <button data-mana-component="button" role="button" class="button_a22cb0 md_a22cb0 color-mix_a22cb0" type="button" aria-label="Fechar" data-captcha-close="true"><div class="buttonChildrenWrapper_a22cb0"><div class="buttonChildren_a22cb0"><svg class="icon_a22cb0" aria-hidden="true" role="img" xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24"><path fill="currentColor" d="M19.3 20.7a1 1 0 0 0 1.4-1.4L13.42 12l7.3-7.3a1 1 0 0 0-1.42-1.4L12 10.58l-7.3-7.3a1 1 0 0 0-1.4 1.42L10.58 12l-7.3 7.3a1 1 0 1 0 1.42 1.4L12 13.42l7.3 7.3Z"></path></svg></div></div></button>
                    </div>
                  </div>
                  <h1 class="heading-xl/semibold_cf4812 defaultColor__5345c headerTitle__8a031" data-text-variant="heading-xl/semibold" style="color:var(--text-strong);">Espere! Você é humano?</h1>
                  <div class="headerSubtitleWrapper__8a031"><div class="text-md/normal_cf4812 headerSubtitle__8a031" data-text-variant="text-md/normal" style="color:var(--text-subtle);">Confirme que você não é um robô.</div></div>
                </div>
              </header>
            </div>
            <div class="bodySpacerTop__8a031"></div>
            <div class="body__8a031 scrollbarGutterStable_d125d2 auto_d125d2 scrollerBase_d125d2" dir="ltr" style="overflow:hidden scroll;">
              <main class="bodyInner__8a031"><div class="captchaContainer_deee3a manaDesktopModal_deee3a"><div id="app-hcaptcha-mount" class="hcaptchaMount_local"></div></div><div class="hcaptchaMessage_local" data-captcha-message="true" aria-live="polite"></div></main>
            </div>
            <div class="bodySpacerBottom__8a031"></div>
          </div>
        </div>
      </div>
    </div>`;
}

async function requestCaptchaToken() {
  const config = await getCaptchaConfig();
  if (!config?.configured || !config?.sitekey) {
    throw new Error("Verificação humana não configurada.");
  }
  if (["127.0.0.1", "localhost"].includes(location.hostname.toLowerCase())) {
    throw new Error(`Abra a aplicação por ${config.localHostname || "o hostname local configurado"} para usar hCaptcha.`);
  }

  const api = await ensureHCaptchaApi();
  const mount = document.createElement("div");
  mount.dataset.appHcaptchaInvisible = "true";
  document.body.appendChild(mount);

  let widgetId = null;
  const retryableExecutionErrors = new Set(["challenge-error", "internal-error"]);
  const normalizeProviderCode = (value) => {
    const raw = typeof value === "string" ? value : (value?.code || value?.name || "unknown");
    return String(raw || "unknown").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 64) || "unknown";
  };
  const providerFailure = (code) => {
    const error = new Error(
      code === "rate-limited"
        ? "Muitas tentativas de confirmação. Aguarde um instante e tente novamente."
        : "Não foi possível concluir a confirmação humana. Tente novamente."
    );
    error.code = `hcaptcha_${code}`;
    return error;
  };

  try {
    widgetId = api.render(mount, {
      sitekey: config.sitekey,
      size: "invisible",
      theme: "light",
      hl: "pt-BR",
      "error-callback": (value) => {
        const code = normalizeProviderCode(value);
        console.warn(`[hcaptcha] provider-error code=${code} mode=invisible`);
      },
      "expired-callback": () => {
        console.warn("[hcaptcha] token-expired mode=invisible");
      }
    });

    for (let attempt = 1; attempt <= 2; attempt += 1) {
      try {
        const execution = await api.execute(widgetId, { async: true });
        const token = String(execution?.response || "").trim();
        if (!token) throw "missing-token";
        console.info(`[hcaptcha] invisible-success attempt=${attempt}`);
        return token;
      } catch (value) {
        const code = normalizeProviderCode(value);
        if (code === "challenge-closed") {
          console.info("[hcaptcha] challenge-closed mode=invisible");
          throw new DOMException("Verificação humana cancelada.", "AbortError");
        }

        const canRetry = attempt === 1 && retryableExecutionErrors.has(code);
        if (!canRetry) {
          console.warn(`[hcaptcha] invisible-failed code=${code} attempt=${attempt}`);
          throw providerFailure(code);
        }

        // hCaptcha documents challenge-error/internal-error in fully programmatic
        // invisible mode as retryable by invoking execute again. The retry is
        // automatic so one user login intent never turns into a second checkbox click.
        console.warn(`[hcaptcha] invisible-retry code=${code} attempt=${attempt}`);
        try { api.reset(widgetId); } catch (_) {}
        await new Promise((resolve) => window.setTimeout(resolve, 250));
      }
    }

    throw providerFailure("unknown");
  } finally {
    if (widgetId !== null && api?.remove) {
      try { api.remove(widgetId); } catch (_) {}
    }
    mount.remove();
  }
}


export { captchaLayer, prewarmCaptcha, requestCaptchaToken };
