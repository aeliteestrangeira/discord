(() => {
  "use strict";

  const elements = {
    notice: document.getElementById("notice"),
    accessSection: document.getElementById("access-section"),
    accessMessage: document.getElementById("access-message"),
    loginLink: document.getElementById("login-link"),
    logoutButton: document.getElementById("logout-button"),
    mfaSection: document.getElementById("mfa-section"),
    mfaMessage: document.getElementById("mfa-message"),
    enrollButton: document.getElementById("enroll-button"),
    enrollment: document.getElementById("enrollment"),
    qr: document.getElementById("totp-qr"),
    secret: document.getElementById("totp-secret"),
    verifyForm: document.getElementById("verify-form"),
    code: document.getElementById("totp-code"),
    dashboard: document.getElementById("dashboard-section"),
    adminEmail: document.getElementById("admin-email"),
    metricUsers: document.getElementById("metric-users"),
    metricConfirmed: document.getElementById("metric-confirmed"),
    metricAdmins: document.getElementById("metric-admins"),
    usersBody: document.getElementById("users-body"),
    refreshButton: document.getElementById("refresh-button"),
  };

  let factorId = "";

  function runtime() {
    if (!window.AppCloudRuntime?.isCloudMode()) throw new Error("Painel cloud indisponÃ­vel nesta origem.");
    return window.AppCloudRuntime;
  }

  function setNotice(message, kind = "") {
    elements.notice.textContent = message;
    elements.notice.className = `notice${kind ? ` ${kind}` : ""}`;
  }

  function setBusy(button, busy) {
    if (!button) return;
    button.disabled = busy;
    button.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function formatDate(value) {
    if (!value) return "Nunca";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "IndisponÃ­vel" : date.toLocaleString("pt-BR");
  }

  function addCell(row, value) {
    const cell = document.createElement("td");
    cell.textContent = String(value || "—");
    row.appendChild(cell);
  }

  function renderUsers(users) {
    elements.usersBody.replaceChildren();
    for (const user of Array.isArray(users) ? users : []) {
      const row = document.createElement("tr");
      addCell(row, user.email);
      addCell(row, user.username);
      addCell(row, user.emailConfirmed ? "Confirmado" : "Pendente");
      addCell(row, formatDate(user.lastSignInAt));
      elements.usersBody.appendChild(row);
    }
  }

  function showDenied(message, loginRequired = false) {
    elements.accessSection.hidden = false;
    elements.accessMessage.textContent = message;
    elements.loginLink.hidden = !loginRequired;
    elements.mfaSection.hidden = true;
    elements.dashboard.hidden = true;
    setNotice(message, "error");
  }

  async function showMfa() {
    elements.accessSection.hidden = true;
    elements.mfaSection.hidden = false;
    elements.dashboard.hidden = true;
    const result = await runtime().mfaStatus();
    if (result.error) throw new Error(result.error.message);

    const verified = result.data.factors.find((factor) =>
      factor.factorType === "totp" && factor.status === "verified"
    );
    if (verified) {
      factorId = verified.id;
      elements.mfaMessage.textContent = "Digite o cÃ³digo atual do autenticador para elevar a sessÃ£o a AAL2.";
      elements.enrollButton.hidden = true;
      elements.enrollment.hidden = true;
      elements.verifyForm.hidden = false;
      elements.code.focus();
    } else {
      elements.mfaMessage.textContent = "Esta conta administrativa ainda nÃ£o possui um segundo fator verificado.";
      elements.enrollButton.hidden = false;
      elements.verifyForm.hidden = true;
    }
    setNotice("Administrador identificado. MFA AAL2 ainda Ã© obrigatÃ³rio.");
  }

  function showDashboard(data) {
    elements.accessSection.hidden = true;
    elements.mfaSection.hidden = true;
    elements.dashboard.hidden = false;
    elements.logoutButton.hidden = false;
    elements.adminEmail.textContent = data.user?.email || "Administrador";
    elements.metricUsers.textContent = String(data.metrics?.authUsers ?? "—");
    elements.metricConfirmed.textContent = String(data.metrics?.confirmedEmails ?? "—");
    elements.metricAdmins.textContent = String(data.metrics?.enabledAdmins ?? "—");
    renderUsers(data.users);
    setNotice("Acesso administrativo validado no servidor com MFA AAL2.", "success");
  }

  async function refresh() {
    setBusy(elements.refreshButton, true);
    try {
      const gate = await runtime().adminGate();
      elements.logoutButton.hidden = gate.status === 401;
      if (gate.status === 401) {
        showDenied("Entre com a conta administrativa para continuar.", true);
        return;
      }
      if (gate.data?.adminEligible !== true && gate.data?.admin !== true) {
        showDenied("Esta conta nÃ£o estÃ¡ autorizada como administradora.");
        elements.logoutButton.hidden = false;
        return;
      }
      if (gate.data?.admin === true && gate.data?.aal === "aal2") {
        showDashboard(gate.data);
        return;
      }
      if (gate.data?.mfaRequired === true) {
        await showMfa();
        elements.logoutButton.hidden = false;
        return;
      }
      throw new Error("Resposta de autorizaÃ§Ã£o invÃ¡lida.");
    } catch (error) {
      showDenied(error?.message || "NÃ£o foi possÃ­vel validar o acesso administrativo.");
    } finally {
      setBusy(elements.refreshButton, false);
    }
  }

  elements.enrollButton.addEventListener("click", async () => {
    setBusy(elements.enrollButton, true);
    try {
      const result = await runtime().enrollAdminTotp();
      if (result.error) throw new Error(result.error.message);
      factorId = result.data.factorId;
      if (!/^data:image\/(?:svg\+xml|png);/i.test(result.data.qrCode)) {
        throw new Error("Formato de QR Code inesperado.");
      }
      elements.qr.src = result.data.qrCode;
      elements.secret.textContent = result.data.secret;
      elements.enrollment.hidden = false;
      elements.verifyForm.hidden = false;
      elements.enrollButton.hidden = true;
      elements.code.focus();
      setNotice("MFA iniciado. Confirme o cÃ³digo para concluir a ativaÃ§Ã£o.");
    } catch (error) {
      setNotice(error?.message || "Falha ao ativar MFA.", "error");
    } finally {
      setBusy(elements.enrollButton, false);
    }
  });

  elements.verifyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!elements.verifyForm.checkValidity() || !factorId) return;
    const submit = elements.verifyForm.querySelector('button[type="submit"]');
    setBusy(submit, true);
    try {
      const result = await runtime().verifyAdminTotp(factorId, elements.code.value);
      if (result.error) throw new Error(result.error.message);
      elements.code.value = "";
      factorId = "";
      elements.qr.removeAttribute("src");
      elements.secret.textContent = "";
      await refresh();
    } catch (error) {
      setNotice(error?.message || "CÃ³digo TOTP recusado.", "error");
      elements.code.select();
    } finally {
      setBusy(submit, false);
    }
  });

  elements.refreshButton.addEventListener("click", refresh);
  elements.logoutButton.addEventListener("click", async () => {
    setBusy(elements.logoutButton, true);
    await runtime().logout().catch(() => null);
    location.replace(new URL("../login.html", location.href).href);
  });

  refresh();
})();
