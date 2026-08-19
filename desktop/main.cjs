"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { app, BrowserWindow, dialog, ipcMain, net, session } = require("electron");
const { APP_URL } = require("./constants.cjs");
const {
  prepareLocalRuntime, waitForBackend, stopBackend, dataPaths,
  privateBootstrapPresent, importPrivateBootstrap, log
} = require("./backend.cjs");
const { hardenWebContents, installPermissionPolicy, isAppUrl } = require("./security.cjs");
const { initializeUpdater, checkForUpdates, installDownloadedUpdate } = require("./updater.cjs");

app.enableSandbox();

const dataRoot = path.join(
  process.env.LOCALAPPDATA || app.getPath("appData"),
  "AEliteEstrangeira", "DiscordDesktop"
);
fs.mkdirSync(path.join(dataRoot, "electron"), { recursive: true });
app.setPath("userData", path.join(dataRoot, "electron"));

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();

let mainWindow = null;
let quittingAfterStop = false;
let backendStarted = false;

const HCAPTCHA_NETWORK_FILTER = Object.freeze({
  urls: ["https://hcaptcha.com/*", "https://*.hcaptcha.com/*"]
});

function sanitizeNetworkField(value, maxLength = 96) {
  return String(value || "unknown")
    .replace(/[^a-zA-Z0-9._:/-]/g, "_")
    .slice(0, maxLength) || "unknown";
}

function safeNetworkTarget(value) {
  try {
    const parsed = new URL(String(value || ""));
    const host = parsed.hostname.toLowerCase();
    const pathname = parsed.pathname || "/";
    return `${parsed.protocol}//${host}${pathname.slice(0, 180)}`;
  } catch (_) {
    return "invalid-url";
  }
}

function installHCaptchaNetworkDiagnostics(desktopSession) {
  const webRequest = desktopSession?.webRequest;
  if (!webRequest) {
    log("[hcaptcha-net] diagnostics-unavailable");
    return;
  }

  webRequest.onErrorOccurred(HCAPTCHA_NETWORK_FILTER, (details = {}) => {
    log(
      `[hcaptcha-net] error target=${safeNetworkTarget(details.url)} ` +
      `method=${sanitizeNetworkField(details.method, 12)} ` +
      `type=${sanitizeNetworkField(details.resourceType, 24)} ` +
      `error=${sanitizeNetworkField(details.error, 80)}`
    );
  });

  webRequest.onCompleted(HCAPTCHA_NETWORK_FILTER, (details = {}) => {
    const status = Number(details.statusCode || 0);
    if (status < 400) return;
    log(
      `[hcaptcha-net] http target=${safeNetworkTarget(details.url)} ` +
      `method=${sanitizeNetworkField(details.method, 12)} ` +
      `type=${sanitizeNetworkField(details.resourceType, 24)} status=${status}`
    );
  });

  log("[hcaptcha-net] diagnostics-installed");
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 650,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#111214",
    title: "Discord Desktop",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      nodeIntegrationInWorker: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      webviewTag: false,
      devTools: process.env.DISCORD_DESKTOP_DEVTOOLS === "1",
      spellcheck: true,
      partition: "persist:discord-desktop"
    }
  });

  hardenWebContents(win.webContents);
  win.once("ready-to-show", () => win.show());
  win.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    if (!isMainFrame || errorCode === -3) return;
    log(`did-fail-load ${errorCode} ${errorDescription} ${validatedURL}`);
  });
  win.webContents.on("console-message", (details) => {
    const message = String(details?.message || "");
    if (!message.startsWith("[hcaptcha]")) return;
    log(`renderer ${message.slice(0, 300)}`);
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    log(`renderer-gone reason=${details.reason} exitCode=${details.exitCode}`);
  });
  return win;
}

async function maybeImportPrivateBootstrap() {
  if (!app.isPackaged) return;
  const paths = dataPaths(dataRoot);
  if (privateBootstrapPresent(paths)) return;

  const answer = await dialog.showMessageBox({
    type: "info",
    title: "Configuracao privada",
    message: "Nenhuma configuracao privada persistente foi encontrada.",
    detail: "Se voce veio da Desktop Alpha, execute MIGRATE_ALPHA_DATA.bat na pasta antiga antes de instalar. Como alternativa, selecione agora o arquivo SUPABASE_PRIVILEGED.env. Nenhuma credencial e enviada ao GitHub.",
    buttons: ["Selecionar arquivo", "Continuar sem configurar", "Fechar"],
    defaultId: 0,
    cancelId: 2,
    noLink: true
  });
  if (answer.response === 2) throw new Error("Inicializacao cancelada: configuracao privada ausente.");
  if (answer.response !== 0) return;

  const selected = await dialog.showOpenDialog({
    title: "Selecionar SUPABASE_PRIVILEGED.env",
    properties: ["openFile"],
    filters: [{ name: "Environment file", extensions: ["env"] }, { name: "Todos os arquivos", extensions: ["*"] }]
  });
  if (selected.canceled || selected.filePaths.length !== 1) return;
  importPrivateBootstrap(selected.filePaths[0], paths);
}

function senderAllowed(event) {
  const url = event?.senderFrame?.url || event?.sender?.getURL?.() || "";
  return isAppUrl(url);
}

function registerDesktopIpc() {
  ipcMain.handle("desktop:version", (event) => senderAllowed(event) ? app.getVersion() : null);
  ipcMain.handle("desktop:check-for-updates", async (event) => {
    if (!senderAllowed(event) || !app.isPackaged) return { ok: false, reason: "not-allowed" };
    return checkForUpdates({ manual: true });
  });
  ipcMain.handle("desktop:install-update", (event) => {
    if (!senderAllowed(event) || !app.isPackaged) return false;
    return installDownloadedUpdate();
  });
}

async function startDesktop() {
  const desktopSession = session.fromPartition("persist:discord-desktop");
  installPermissionPolicy(desktopSession);
  installHCaptchaNetworkDiagnostics(desktopSession);
  registerDesktopIpc();
  mainWindow = createWindow();

  try {
    await maybeImportPrivateBootstrap();
    const runtime = await prepareLocalRuntime({
      packaged: app.isPackaged,
      resourcesPath: process.resourcesPath,
      dataRoot
    });
    backendStarted = true;
    await waitForBackend((url, options) => net.fetch(url, options), 45000);
    await mainWindow.loadURL(APP_URL);

    if (app.isPackaged) {
      initializeUpdater({ window: mainWindow, dataRoot, logger: log });
      void checkForUpdates({ manual: false, startup: true });
    }
    log(`desktop ready mode=${runtime.mode} version=${app.getVersion()}`);
  } catch (error) {
    log(`startup-failure: ${error.stack || error.message}`);
    await dialog.showMessageBox({
      type: "error",
      title: "Falha ao iniciar o aplicativo",
      message: "O site local nao conseguiu iniciar dentro do aplicativo desktop.",
      detail: `${error.message}\n\nDados/logs: ${dataRoot}`,
      buttons: ["Fechar"],
      defaultId: 0,
      noLink: true
    });
    app.quit();
  }
}

app.on("second-instance", () => {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
});

app.on("certificate-error", (_event, _webContents, url, error, _certificate, callback) => {
  log(`certificate-error target=${safeNetworkTarget(url)} error=${sanitizeNetworkField(error, 80)}`);
  callback(false);
});

app.on("before-quit", (event) => {
  if (quittingAfterStop || !backendStarted) return;
  event.preventDefault();
  quittingAfterStop = true;
  void stopBackend({ packaged: app.isPackaged }).finally(() => app.quit());
});

app.on("window-all-closed", () => app.quit());

if (gotLock) {
  app.whenReady().then(startDesktop).catch((error) => {
    log(`ready-failure: ${error.stack || error.message}`);
    app.quit();
  });
}
