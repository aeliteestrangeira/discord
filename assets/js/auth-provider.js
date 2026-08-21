(() => {
  "use strict";

  let csrfPromise;
  let cloudRuntimePromise;

  function isCloudMode() {
    return location.origin === "https://aeliteestrangeira.github.io" &&
      location.pathname.toLowerCase().startsWith("/discord/");
  }

  function ensureCloudRuntime() {
    if (window.AppCloudRuntime) return Promise.resolve(window.AppCloudRuntime);
    if (cloudRuntimePromise) return cloudRuntimePromise;
    cloudRuntimePromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-app-cloud-runtime="true"]');
      const script = existing || document.createElement("script");
      const current = document.querySelector('script[data-app-auth-provider="true"]');

      const loaded = () => {
        if (!window.AppCloudRuntime) {
          reject(new Error("Cloud runtime indisponível."));
          return;
        }
        resolve(window.AppCloudRuntime);
      };
      script.addEventListener("load", loaded, { once: true });
      script.addEventListener("error", () => reject(new Error("Falha ao carregar cloud runtime.")), { once: true });

      if (!existing) {
        script.src = new URL("cloud-runtime.js", current?.src || location.href).href;
        script.async = true;
        script.dataset.appCloudRuntime = "true";
        document.head.appendChild(script);
      } else if (window.AppCloudRuntime) {
        loaded();
      }
    }).catch((error) => {
      cloudRuntimePromise = undefined;
      throw error;
    });
    return cloudRuntimePromise;
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

  async function csrfToken() {
    if (!csrfPromise) {
      csrfPromise = fetch("/api/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Accept": "application/json" }
      }).then(async (response) => {
        const body = await response.json().catch(() => ({}));
        if (!response.ok || !body.csrfToken) throw new Error("Falha ao inicializar a sessão local.");
        return body.csrfToken;
      });
    }
    return csrfPromise;
  }

  async function get(path) {
    const response = await fetch(path, {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json" }
    });
    const body = await response.json().catch(() => ({}));
    return { response, body };
  }

  async function post(path, payload) {
    const token = await csrfToken();
    const response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": token
      },
      body: JSON.stringify(payload)
    });
    const body = await response.json().catch(() => ({}));
    if (body && body.csrfToken) csrfPromise = Promise.resolve(body.csrfToken);
    if (response.status === 401 || response.status === 403) csrfPromise = undefined;
    return { response, body };
  }

  async function signIn(identifier, password, hcaptchaToken) {
    if (isCloudMode()) return (await ensureCloudRuntime()).signIn(identifier, password, hcaptchaToken);
    const { response, body } = await post("/api/auth/login", { identifier, password, hcaptchaToken });
    if (!body.configured && response.status === 503) {
      return { configured: false, data: null, error: body.error || null };
    }
    if (!response.ok || !body.ok) {
      return { configured: true, data: null, error: body.error || { code: "auth_error", message: "Falha de autenticação." } };
    }
    return { configured: true, data: body, error: null };
  }

  async function signUp(email, password, profile, marketingOptIn, hcaptchaToken) {
    if (isCloudMode()) return (await ensureCloudRuntime()).signUp(email, password, profile, marketingOptIn, hcaptchaToken);
    const { response, body } = await post("/api/auth/register", { email, password, profile, marketingOptIn, hcaptchaToken });
    if (!body.configured && response.status === 503) {
      return { configured: false, data: null, error: body.error || null };
    }
    if (!response.ok || !body.ok) {
      return { configured: true, data: null, error: body.error || { code: "register_error", message: "Falha no cadastro." } };
    }
    return { configured: true, data: body, error: null };
  }

  async function checkUsername(username) {
    if (isCloudMode()) return (await ensureCloudRuntime()).usernameAvailable(username);
    const { response, body } = await post("/api/auth/username/check", { username });
    if (!response.ok || !body.ok) {
      return { available: null, error: body.error || { code: "username_check_error", message: "Não foi possível verificar o nome de usuário." } };
    }
    return { available: body.available === true, error: null };
  }

  async function suggestUsername(displayName) {
    if (isCloudMode()) return (await ensureCloudRuntime()).suggestUsername(displayName);
    const { response, body } = await post("/api/auth/username/suggest", { displayName });
    if (!response.ok || !body.ok) {
      return { suggestion: null, error: body.error || { code: "username_suggestion_error", message: "Não foi possível gerar uma sugestão." } };
    }
    return { suggestion: body.suggestion || null, error: null };
  }


  async function requestLoginLink(identifier) {
    if (isCloudMode()) return (await ensureCloudRuntime()).requestLoginLink(identifier, arguments[1]);
    const { response, body } = await post("/api/auth/login-link", { identifier });
    if (!body.configured && response.status === 503) {
      return { configured: false, data: null, error: body.error || null };
    }
    if (!response.ok || !body.ok) {
      return { configured: true, data: null, error: body.error || { code: "login_link_error", message: "Não foi possível solicitar o link de acesso." } };
    }
    return { configured: true, data: body, error: null };
  }


  async function startPasskeyAuthentication() {
    if (isCloudMode()) return (await ensureCloudRuntime()).startPasskeyAuthentication();
    const { response, body } = await post("/api/auth/passkey/options", {});
    if (!body.configured && response.status === 503) {
      return { configured: false, data: null, error: body.error || null };
    }
    if (!response.ok || !body.ok) {
      return { configured: true, data: null, error: body.error || { code: "passkey_options_error", message: "Não foi possível iniciar a chave de acesso." } };
    }
    return { configured: true, data: body, error: null };
  }

  async function verifyPasskeyAuthentication(challengeId, credential) {
    if (isCloudMode()) return (await ensureCloudRuntime()).verifyPasskeyAuthentication(challengeId, credential);
    const { response, body } = await post("/api/auth/passkey/verify", { challengeId, credential });
    if (!body.configured && response.status === 503) {
      return { configured: false, data: null, error: body.error || null };
    }
    if (!response.ok || !body.ok) {
      return { configured: true, data: null, error: body.error || { code: "passkey_verify_error", message: "A chave de acesso não foi aceita." } };
    }
    return { configured: true, data: body, error: null };
  }

  async function session() {
    if (isCloudMode()) return (await ensureCloudRuntime()).session();
    const response = await fetch("/api/session", { credentials: "same-origin", cache: "no-store" });
    return response.ok ? response.json() : { authenticated: false };
  }

  async function validateSession() {
    if (isCloudMode()) return (await ensureCloudRuntime()).validateSession();
    const { response, body } = await get("/api/session/validate");
    if (!response.ok || !body.ok || body.authenticated !== true) {
      return { data: null, error: body.error || { code: "session_revoked", message: "A sessão não é mais válida." }, status: response.status };
    }
    return { data: body, error: null, status: response.status };
  }

  async function verificationStatus() {
    if (isCloudMode()) return (await ensureCloudRuntime()).verificationStatus();
    const { response, body } = await post("/api/auth/verification/status", {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "verification_status_error", message: "Não foi possível atualizar a verificação." } };
    }
    return { data: body, error: null };
  }

  async function resendConfirmation() {
    if (isCloudMode()) return (await ensureCloudRuntime()).resendConfirmation();
    const { response, body } = await post("/api/auth/resend-confirmation", {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "resend_confirmation_error", message: "Não foi possível reenviar o e-mail." } };
    }
    return { data: body, error: null };
  }

  async function sendFriendRequest(username, hcaptchaToken) {
    const { response, body } = await post("/api/friends/requests", { username, hcaptchaToken });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "friend_request_error", message: "Não foi possível enviar o pedido de amizade." } };
    }
    return { data: body, error: null };
  }

  async function listPendingFriendRequests() {
    const { response, body } = await get("/api/friends/requests/pending");
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "friend_requests_list_error", message: "Não foi possível carregar os pedidos pendentes." } };
    }
    return { data: body, error: null };
  }

  async function cancelFriendRequest(requestId) {
    const encoded = encodeURIComponent(String(requestId || ""));
    const { response, body } = await post(`/api/friends/requests/${encoded}/cancel`, {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "friend_request_cancel_error", message: "Não foi possível cancelar o pedido de amizade." } };
    }
    return { data: body, error: null };
  }

  async function acceptFriendRequest(requestId) {
    const encoded = encodeURIComponent(String(requestId || ""));
    const { response, body } = await post(`/api/friends/requests/${encoded}/accept`, {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "friend_request_accept_error", message: "Não foi possível aceitar o pedido de amizade." } };
    }
    return { data: body, error: null };
  }

  async function ignoreFriendRequest(requestId) {
    const encoded = encodeURIComponent(String(requestId || ""));
    const { response, body } = await post(`/api/friends/requests/${encoded}/ignore`, {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "friend_request_ignore_error", message: "Não foi possível ignorar o pedido de amizade." } };
    }
    return { data: body, error: null };
  }

  async function createGuild({ name, templateKey, audience, icon = null }) {
    const token = await csrfToken();
    const form = new FormData();
    form.append("name", String(name || ""));
    form.append("templateKey", String(templateKey || "custom"));
    form.append("audience", String(audience || "friends"));
    if (icon instanceof File) form.append("icon", icon, icon.name || "server-icon");
    const response = await fetch("/api/guilds", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: { "Accept": "application/json", "X-CSRF-Token": token },
      body: form
    });
    const body = await response.json().catch(() => ({}));
    if (body && body.csrfToken) csrfPromise = Promise.resolve(body.csrfToken);
    if (response.status === 401 || response.status === 403) csrfPromise = undefined;
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "guild_create_error", message: "Não foi possível criar o servidor." } };
    }
    return { data: body, error: null };
  }

  async function joinVoice(guildId, channelId) {
    const { response, body } = await post("/api/voice/join", { guildId, channelId });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "voice_join_error", message: "Não foi possível conectar ao canal de voz." } };
    }
    return { data: body, error: null };
  }

  async function voiceState(voiceSessionId) {
    const { response, body } = await post("/api/voice/state", { voiceSessionId });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "voice_state_error", message: "Não foi possível atualizar o canal de voz." }, status: response.status };
    }
    return { data: body, error: null, status: response.status };
  }

  async function sendVoiceSignal(voiceSessionId, targetSessionId, type, payload) {
    const { response, body } = await post("/api/voice/signal", { voiceSessionId, targetSessionId, type, payload });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "voice_signal_error", message: "Não foi possível negociar a conexão de voz." }, status: response.status };
    }
    return { data: body, error: null, status: response.status };
  }

  async function leaveVoice(voiceSessionId) {
    const { response, body } = await post("/api/voice/leave", { voiceSessionId });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "voice_leave_error", message: "Não foi possível encerrar a sessão de voz." } };
    }
    return { data: body, error: null };
  }

  async function changeEmail(email, password) {
    if (isCloudMode()) return (await ensureCloudRuntime()).changeEmail(email, password);
    const { response, body } = await post("/api/auth/change-email", { email, password });
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "email_change_error", message: "Não foi possível alterar o e-mail." } };
    }
    return { data: body, error: null };
  }

  async function logout() {
    if (isCloudMode()) return (await ensureCloudRuntime()).logout();
    const { response, body } = await post("/api/auth/logout", {});
    if (!response.ok || !body.ok) {
      return { data: null, error: body.error || { code: "logout_error", message: "Não foi possível sair agora." } };
    }
    broadcastSessionRevoked();
    return { data: body, error: null };
  }

  window.AppAuthProvider = Object.freeze({
    signIn, signUp, checkUsername, suggestUsername, requestLoginLink,
    startPasskeyAuthentication, verifyPasskeyAuthentication, session, validateSession,
    verificationStatus, resendConfirmation, sendFriendRequest, listPendingFriendRequests, cancelFriendRequest, acceptFriendRequest, ignoreFriendRequest,
    createGuild, joinVoice, voiceState, sendVoiceSignal, leaveVoice, changeEmail, logout
  });
})();
