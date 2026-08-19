"use strict";

const path = require("node:path");
const { app, BrowserWindow, dialog, net, session } = require("electron");
const { APP_URL } = require("./constants.cjs");
const { prepareLocalRuntime, waitForBackend, stopBackend, LOG, log } = require("./backend.cjs");
const { hardenWebContents, installPermissionPolicy } = require("./security.cjs");

app.enableSandbox();

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

let mainWindow = null;
let quittingAfterStop = false;
let backendStarted = false;

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
    if (!isMainFrame) return;
    log(`did-fail-load ${errorCode} ${errorDescription} ${validatedURL}`);
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    log(`renderer-gone reason=${details.reason} exitCode=${details.exitCode}`);
  });

  return win;
}

async function startDesktop() {
  installPermissionPolicy(session.fromPartition("persist:discord-desktop"));
  mainWindow = createWindow();

  try {
    await prepareLocalRuntime();
    backendStarted = true;
    await waitForBackend((url, options) => net.fetch(url, options), 30000);
    await mainWindow.loadURL(APP_URL);
  } catch (error) {
    log(`startup-failure: ${error.stack || error.message}`);
    await dialog.showMessageBox({
      type: "error",
      title: "Falha ao iniciar o aplicativo",
      message: "O site local nao conseguiu iniciar dentro do aplicativo desktop.",
      detail: `${error.message}\n\nLog: ${LOG}`,
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
  log(`certificate-error url=${url} error=${error}`);
  // Fail closed. The local CA must be trusted by ensure_local_tls.ps1.
  callback(false);
});

app.on("before-quit", (event) => {
  if (quittingAfterStop || !backendStarted) return;
  event.preventDefault();
  quittingAfterStop = true;
  void stopBackend().finally(() => app.quit());
});

app.on("window-all-closed", () => {
  app.quit();
});

if (gotLock) {
  app.whenReady().then(startDesktop).catch((error) => {
    log(`ready-failure: ${error.stack || error.message}`);
    app.quit();
  });
}
