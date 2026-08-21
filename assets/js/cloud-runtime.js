(() => {
  "use strict";

  const VERSION = "4.3.8";
  const FRONTEND_ORIGIN = "https://aeliteestrangeira.github.io";
  const APP_BASE_PATH = "/discord/";
  const BOOTSTRAP_SUPABASE_URL = "https://kwekrdluscriubyfolri.supabase.co";
  const BOOTSTRAP_PUBLISHABLE_KEY = "sb_publishable_kRPTrvZZfc2kQlYpF-Q9CA_88jZ9YDT";
  const PUBLIC_CONFIG_URL = `${BOOTSTRAP_SUPABASE_URL}/functions/v1/public-config`;
  const USERNAME_AVAILABILITY_URL = `${BOOTSTRAP_SUPABASE_URL}/functions/v1/username-availability`;
  const ADMIN_GATE_URL = `${BOOTSTRAP_SUPABASE_URL}/functions/v1/admin-gate`;
  const SUPABASE_JS_URL = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.112.3/dist/umd/supabase.js";

  let configPromise;
  let sdkPromise;
  let clientPromise;

  function isCloudMode() {
    return location.origin === FRONTEND_ORIGIN &&
      location.pathname.toLowerCase().startsWith(APP_BASE_PATH);
  }

  async function publicConfig() {
    if (!isCloudMode()) throw new Error("Cloud runtime fora da origem autorizada.");
    if (!configPromise) {
      configPromise = fetch(PUBLIC_CONFIG_URL, {
        method: "GET",
        mode: "cors",
        cache: "no-store",
        headers: {
          "Accept": "application/json",
          "apikey": BOOTSTRAP_PUBLISHABLE_KEY,
        },
      }).then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok || body?.ok !== true) throw new Error("Configuração cloud indisponível.");
        if (body.frontendOrigin !== FRONTEND_ORIGIN) throw new Error("Origem cloud inesperada.");
        if (body.appBasePath !== APP_BASE_PATH) throw new Error("Base path cloud inesperado.");
        if (body.supabaseUrl !== BOOTSTRAP_SUPABASE_URL) throw new Error("Projeto Supabase inesperado.");
        if (typeof body.publishableKey !== "string" || !body.publishableKey.startsWith("sb_publishable_")) {
          throw new Error("Chave pública cloud inválida.");
        }
        if (!body.hcaptcha?.configured || !body.hcaptcha?.sitekey) {
          throw new Error("hCaptcha cloud não configurado.");
        }
        return Object.freeze(body);
      }).catch((error) => {
        configPromise = undefined;
        throw error;
      });
    }
    return configPromise;
  }

  function loadSdk() {
    if (window.supabase?.createClient) return Promise.resolve(window.supabase);
    if (sdkPromise) return sdkPromise;

    sdkPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-app-supabase-sdk="true"]');
      const script = existing || document.createElement("script");
      let settled = false;

      const finish = () => {
        if (settled) return;
        settled = true;
        if (!window.supabase?.createClient) {
          reject(new Error("Supabase SDK indisponível."));
          return;
        }
        resolve(window.supabase);
      };
      const fail = () => {
        if (settled) return;
        settled = true;
        reject(new Error("Falha ao carregar Supabase SDK."));
      };

      script.addEventListener("load", finish, { once: true });
      script.addEventListener("error", fail, { once: true });

      if (!existing) {
        script.src = SUPABASE_JS_URL;
        script.async = true;
        script.defer = true;
        script.crossOrigin = "anonymous";
        script.dataset.appSupabaseSdk = "true";
        document.head.appendChild(script);
      } else if (window.supabase?.createClient) {
        finish();
      }
    }).catch((error) => {
      sdkPromise = undefined;
      document.querySelector('script[data-app-supabase-sdk="true"]')?.remove();
      throw error;
    });
    return sdkPromise;
  }

  async function client() {
    if (!clientPromise) {
      clientPromise = Promise.all([publicConfig(), loadSdk()]).then(([cfg, sdk]) => sdk.createClient(
        cfg.supabaseUrl,
        cfg.publishableKey,
        {
          auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: false,
            flowType: "pkce",
          },
          global: {
            headers: { "X-Client-Info": `discord-web/${VERSION}` },
          },
        }
      )).catch((error) => {
        clientPromise = undefined;
        throw error;
      });
    }
    return clientPromise;
  }

  async function captchaConfig() {
    const cfg = await publicConfig();
    return Object.freeze({
      configured: cfg.hcaptcha?.configured === true,
      required: true,
      sitekey: String(cfg.hcaptcha?.sitekey || ""),
      localHostname: String(cfg.hcaptcha?.hostname || "aeliteestrangeira.github.io"),
    });
  }

  async function callAdminGate(activeSession) {
    const cfg = await publicConfig();
    const token = String(activeSession?.access_token || "");
    if (!token) {
      return { status: 401, data: { ok: false, admin: false, error: "missing_token" } };
    }
    const response = await fetch(ADMIN_GATE_URL, {
      method: "GET",
      mode: "cors",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "Authorization": `Bearer ${token}`,
        "apikey": cfg.publishableKey,
      },
    });
    const data = await response.json().catch(() => ({
      ok: false,
      admin: false,
      error: "invalid_admin_response",
    }));
    return { status: response.status, data };
  }

  async function adminGate() {
    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.getSession();
    if (error || !data?.session) {
      return { status: 401, data: { ok: false, admin: false, error: "session_missing" } };
    }
    return callAdminGate(data.session);
  }

  async function mfaStatus() {
    const supabaseClient = await client();
    const [aalResult, factorsResult] = await Promise.all([
      supabaseClient.auth.mfa.getAuthenticatorAssuranceLevel(),
      supabaseClient.auth.mfa.listFactors(),
    ]);
    if (aalResult.error || factorsResult.error) {
      return {
        data: null,
        error: {
          code: aalResult.error?.code || factorsResult.error?.code || "mfa_status_error",
          message: "NÃ£o foi possÃ­vel consultar o segundo fator.",
        },
      };
    }
    const factors = Array.isArray(factorsResult.data?.all) ? factorsResult.data.all : [];
    return {
      data: {
        currentLevel: aalResult.data?.currentLevel || "aal1",
        nextLevel: aalResult.data?.nextLevel || "aal1",
        factors: factors.map((factor) => ({
          id: String(factor.id || ""),
          status: String(factor.status || ""),
          factorType: String(factor.factor_type || ""),
          friendlyName: String(factor.friendly_name || ""),
        })),
      },
      error: null,
    };
  }

  async function enrollAdminTotp() {
    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.mfa.enroll({
      factorType: "totp",
      friendlyName: "Discord Web Admin",
    });
    if (error || !data?.id || !data?.totp) {
      return {
        data: null,
        error: {
          code: error?.code || "mfa_enroll_error",
          message: "NÃ£o foi possÃ­vel iniciar o MFA TOTP.",
        },
      };
    }
    return {
      data: {
        factorId: String(data.id),
        qrCode: String(data.totp.qr_code || ""),
        secret: String(data.totp.secret || ""),
      },
      error: null,
    };
  }

  async function verifyAdminTotp(factorId, code) {
    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.mfa.challengeAndVerify({
      factorId: String(factorId || ""),
      code: String(code || "").replace(/\s+/g, ""),
    });
    if (error || !data) {
      return {
        data: null,
        error: {
          code: error?.code || "mfa_verify_error",
          message: "CÃ³digo TOTP invÃ¡lido ou expirado.",
        },
      };
    }
    return { data: { ok: true }, error: null };
  }

  async function profileFor(user) {
    if (!user?.id) return null;
    const supabaseClient = await client();
    const { data, error } = await supabaseClient
      .from("profiles")
      .select("id,username,global_name,date_of_birth,marketing_opt_in")
      .eq("id", user.id)
      .maybeSingle();
    if (error) return null;
    return data || null;
  }

  function normalizeUser(user, profile) {
    if (!user) return null;
    return {
      id: user.id,
      email: user.email || "",
      phone: user.phone || "",
      username: profile?.username || user.user_metadata?.username || "",
      globalName: profile?.global_name || user.user_metadata?.global_name || "",
      emailConfirmed: Boolean(user.email_confirmed_at || user.confirmed_at),
    };
  }

  async function usernameAvailable(username) {
    const cfg = await publicConfig();
    const value = String(username || "").trim().toLowerCase();
    const response = await fetch(USERNAME_AVAILABILITY_URL, {
      method: "POST",
      mode: "cors",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "apikey": cfg.publishableKey,
      },
      body: JSON.stringify({ username: value }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || body?.ok !== true) {
      return {
        available: null,
        error: body?.error || {
          code: "username_check_error",
          message: "Não foi possível verificar o nome de usuário.",
        },
      };
    }
    return { available: body.available === true, error: null };
  }

  function usernameBase(displayName) {
    const normalized = String(displayName || "")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9_.]+/g, "")
      .replace(/\.{2,}/g, ".")
      .replace(/^[._]+|[._]+$/g, "");
    return normalized || "usuario";
  }

  function randomDigits() {
    const bytes = new Uint32Array(1);
    crypto.getRandomValues(bytes);
    return String(bytes[0] % 100000).padStart(5, "0");
  }

  async function suggestUsername(displayName) {
    const base = usernameBase(displayName);
    for (let attempt = 0; attempt < 12; attempt += 1) {
      const suffix = randomDigits();
      const candidate = `${base.slice(0, Math.max(1, 32 - suffix.length))}${suffix}`;
      const result = await usernameAvailable(candidate);
      if (result.available === true) return { suggestion: candidate, error: null };
      if (result.available === null) return { suggestion: null, error: result.error };
    }
    return {
      suggestion: null,
      error: { code: "suggestion_unavailable", message: "Não foi possível gerar uma sugestão agora." },
    };
  }

  async function signIn(identifier, password, captchaToken) {
    const email = String(identifier || "").trim();
    if (!email.includes("@")) {
      return {
        configured: true,
        data: null,
        error: { code: "auth_denied", message: "Na versão Web, entre usando o e-mail da conta." },
      };
    }

    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.signInWithPassword({
      email,
      password: String(password || ""),
      options: { captchaToken: String(captchaToken || "") },
    });

    if (error || !data?.user || !data?.session) {
      return {
        configured: true,
        data: null,
        error: {
          code: error?.code || "auth_denied",
          message: "Não foi possível autenticar com as credenciais informadas.",
        },
      };
    }

    const profile = await profileFor(data.user);
    let adminAccess = null;
    try {
      adminAccess = await callAdminGate(data.session);
    } catch (_) {}
    const adminEligible = adminAccess?.data?.adminEligible === true || adminAccess?.data?.admin === true;
    return {
      configured: true,
      data: {
        ok: true,
        status: "authenticated",
        role: adminEligible ? "admin" : "user",
        redirect: adminEligible ? "/admin" : "channels.html",
        user: normalizeUser(data.user, profile),
      },
      error: null,
    };
  }

  async function signUp(email, password, profile, marketingOptIn, captchaToken) {
    const metadata = {
      username: String(profile?.username || "").trim().toLowerCase(),
      global_name: String(profile?.globalName || profile?.global_name || "").trim(),
      date_of_birth: String(profile?.dateOfBirth || profile?.date_of_birth || "").trim(),
      marketing_opt_in: Boolean(marketingOptIn),
    };

    const availability = await usernameAvailable(metadata.username);
    if (availability.available !== true) {
      return {
        configured: true,
        data: null,
        error: availability.available === false
          ? { code: "username_unavailable", message: "Nome de usuário indisponível." }
          : availability.error,
      };
    }

    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.signUp({
      email: String(email || "").trim(),
      password: String(password || ""),
      options: {
        captchaToken: String(captchaToken || ""),
        emailRedirectTo: `${FRONTEND_ORIGIN}${APP_BASE_PATH}`,
        data: metadata,
      },
    });

    if (error || !data?.user) {
      return {
        configured: true,
        data: null,
        error: {
          code: error?.code === "user_already_exists" ? "registration_denied" : (error?.code || "registration_denied"),
          message: "Não foi possível concluir o cadastro com os dados informados.",
        },
      };
    }

    const hasSession = Boolean(data.session);
    return {
      configured: true,
      data: {
        ok: true,
        status: hasSession ? "authenticated" : "confirmation-pending",
        confirmationPending: !hasSession,
        role: hasSession ? "user" : "pending",
        redirect: hasSession ? "channels.html" : "login.html",
        user: normalizeUser(data.user, metadata),
      },
      error: null,
    };
  }

  async function requestLoginLink(identifier, captchaToken) {
    const email = String(identifier || "").trim();
    if (!email.includes("@")) {
      return {
        configured: true,
        data: null,
        error: { code: "identifier_email_required", message: "Use o e-mail da conta para receber o link." },
      };
    }

    const supabaseClient = await client();
    const { error } = await supabaseClient.auth.signInWithOtp({
      email,
      options: {
        shouldCreateUser: false,
        emailRedirectTo: `${FRONTEND_ORIGIN}${APP_BASE_PATH}`,
        captchaToken: String(captchaToken || ""),
      },
    });

    if (error) {
      return {
        configured: true,
        data: null,
        error: {
          code: error.code || "login_link_error",
          message: "Não foi possível solicitar o link de acesso.",
        },
      };
    }

    return {
      configured: true,
      data: {
        ok: true,
        status: "login-link-requested",
        channel: "email",
        message: "Se a conta existir e estiver apta, as instruções serão enviadas.",
      },
      error: null,
    };
  }

  async function passkeyUnavailable() {
    return {
      configured: false,
      data: null,
      error: {
        code: "passkey_web_transition",
        message: "Chaves de acesso serão ativadas na etapa Web seguinte.",
      },
    };
  }

  async function session() {
    const supabaseClient = await client();
    const callbackUrl = new URL(location.href);
    const authCode = String(callbackUrl.searchParams.get("code") || "").trim();
    if (authCode) {
      const { error: exchangeError } = await supabaseClient.auth.exchangeCodeForSession(authCode);
      callbackUrl.searchParams.delete("code");
      history.replaceState(history.state, "", `${callbackUrl.pathname}${callbackUrl.search}${callbackUrl.hash}`);
      if (exchangeError) return { authenticated: false, role: "anonymous" };
    }
    const { data, error } = await supabaseClient.auth.getSession();
    if (error || !data?.session?.user) return { authenticated: false, role: "anonymous" };
    const profile = await profileFor(data.session.user);
    return {
      authenticated: true,
      role: "user",
      user: normalizeUser(data.session.user, profile),
      expiresAt: data.session.expires_at || null,
    };
  }

  async function validateSession() {
    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.getUser();
    if (error || !data?.user) {
      return {
        data: null,
        error: { code: "session_revoked", message: "A sessão não é mais válida." },
        status: 401,
      };
    }
    const profile = await profileFor(data.user);
    return {
      data: {
        ok: true,
        authenticated: true,
        role: "user",
        user: normalizeUser(data.user, profile),
      },
      error: null,
      status: 200,
    };
  }

  async function verificationStatus() {
    const supabaseClient = await client();
    const { data, error } = await supabaseClient.auth.getUser();
    if (error || !data?.user) {
      return {
        data: null,
        error: { code: "session_revoked", message: "A sessão não é mais válida." },
      };
    }
    const confirmed = Boolean(data.user.email_confirmed_at || data.user.confirmed_at);
    return {
      data: {
        ok: true,
        emailConfirmed: confirmed,
        status: confirmed ? "verified" : "confirmation-pending",
      },
      error: null,
    };
  }

  async function resendConfirmation() {
    const supabaseClient = await client();
    const { data: userData } = await supabaseClient.auth.getUser();
    const email = String(userData?.user?.email || "");
    if (!email) {
      return {
        data: null,
        error: {
          code: "confirmation_session_missing",
          message: "Entre novamente para reenviar a confirmação.",
        },
      };
    }
    const { error } = await supabaseClient.auth.resend({
      type: "signup",
      email,
      options: { emailRedirectTo: `${FRONTEND_ORIGIN}${APP_BASE_PATH}` },
    });
    if (error) {
      return {
        data: null,
        error: {
          code: error.code || "resend_confirmation_error",
          message: "Não foi possível reenviar o e-mail.",
        },
      };
    }
    return { data: { ok: true, status: "confirmation-resent" }, error: null };
  }

  async function changeEmail() {
    return {
      data: null,
      error: {
        code: "change_email_web_transition",
        message: "Alteração de e-mail será ativada na próxima etapa Web.",
      },
    };
  }

  function broadcastSessionRevoked() {
    try {
      const channel = new BroadcastChannel("app-session-events");
      channel.postMessage({ type: "revoked", at: Date.now() });
      channel.close();
    } catch (_) {}
    try {
      localStorage.setItem("app-session-revoked", String(Date.now()));
      localStorage.removeItem("app-session-revoked");
    } catch (_) {}
  }

  async function logout() {
    const supabaseClient = await client();
    const { error } = await supabaseClient.auth.signOut();
    if (error) {
      return {
        data: null,
        error: { code: error.code || "logout_error", message: "Não foi possível sair agora." },
      };
    }
    broadcastSessionRevoked();
    return { data: { ok: true }, error: null };
  }

  window.AppCloudRuntime = Object.freeze({
    version: VERSION,
    isCloudMode,
    publicConfig,
    client,
    captchaConfig,
    usernameAvailable,
    suggestUsername,
    adminGate,
    mfaStatus,
    enrollAdminTotp,
    verifyAdminTotp,
    signIn,
    signUp,
    requestLoginLink,
    startPasskeyAuthentication: passkeyUnavailable,
    verifyPasskeyAuthentication: passkeyUnavailable,
    session,
    validateSession,
    verificationStatus,
    resendConfirmation,
    changeEmail,
    logout,
  });
})();
