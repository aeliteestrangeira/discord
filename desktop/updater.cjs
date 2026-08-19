"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { dialog } = require("electron");
const { autoUpdater } = require("electron-updater");

const MIN_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
let initialized = false;
let downloaded = false;
let mainWindow = null;
let stateFile = null;
let log = () => {};
let lastProgressBucket = -1;

function readState() {
  if (!stateFile) return {};
  try { return JSON.parse(fs.readFileSync(stateFile, "utf8")); } catch (_) { return {}; }
}

function writeState(value) {
  if (!stateFile) return;
  try {
    fs.mkdirSync(path.dirname(stateFile), { recursive: true });
    fs.writeFileSync(stateFile, JSON.stringify(value, null, 2), "utf8");
  } catch (error) {
    log(`[updater] state-write non-fatal: ${error.message}`);
  }
}

function markChecked() {
  const state = readState();
  state.lastCheckAt = Date.now();
  writeState(state);
}

function checkDue() {
  const state = readState();
  const last = Number(state.lastCheckAt || 0);
  return !Number.isFinite(last) || last <= 0 || Date.now() - last >= MIN_CHECK_INTERVAL_MS;
}

async function promptRestart(info) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const version = info?.version || "nova versao";
  const result = await dialog.showMessageBox(mainWindow, {
    type: "info",
    title: "Atualizacao pronta",
    message: `A versao ${version} foi baixada e esta pronta para instalar.`,
    detail: "A aplicacao sera reiniciada para concluir a atualizacao. Seus dados locais ficam fora da pasta do programa e nao sao substituidos.",
    buttons: ["Reiniciar e instalar", "Depois"],
    defaultId: 0,
    cancelId: 1,
    noLink: true
  });
  if (result.response === 0) autoUpdater.quitAndInstall(false, true);
}

function initializeUpdater({ window, dataRoot, logger }) {
  if (initialized) return;
  initialized = true;
  mainWindow = window;
  log = logger || log;
  stateFile = path.join(dataRoot, "updater", "state.json");

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.allowPrerelease = false;

  autoUpdater.on("checking-for-update", () => log("[updater] checking"));
  autoUpdater.on("update-not-available", (info) => {
    markChecked();
    log(`[updater] current ${info?.version || "unknown"}`);
  });
  autoUpdater.on("update-available", async (info) => {
    markChecked();
    lastProgressBucket = -1;
    log(`[updater] available ${info?.version || "unknown"}`);
    try { await autoUpdater.downloadUpdate(); } catch (error) { log(`[updater] download-error: ${error.message}`); }
  });
  autoUpdater.on("download-progress", (progress) => {
    const raw = Math.max(0, Math.min(100, Number(progress?.percent || 0)));
    const bucket = raw >= 100 ? 100 : Math.floor(raw / 5) * 5;
    if (bucket <= lastProgressBucket) return;
    lastProgressBucket = bucket;
    log(`[updater] download ${bucket}%`);
  });
  autoUpdater.on("update-downloaded", (info) => {
    downloaded = true;
    lastProgressBucket = 100;
    log(`[updater] downloaded ${info?.version || "unknown"}`);
    void promptRestart(info);
  });
  autoUpdater.on("error", (error) => log(`[updater] error: ${error.message}`));
}

async function checkForUpdates({ manual = false } = {}) {
  if (!initialized) return { ok: false, reason: "not-initialized" };
  if (!manual && !checkDue()) return { ok: true, skipped: "interval" };
  try {
    markChecked();
    const result = await autoUpdater.checkForUpdates();
    return { ok: true, version: result?.updateInfo?.version || null };
  } catch (error) {
    log(`[updater] check-error: ${error.message}`);
    if (manual && mainWindow && !mainWindow.isDestroyed()) {
      await dialog.showMessageBox(mainWindow, {
        type: "warning",
        title: "Atualizacoes",
        message: "Nao foi possivel verificar atualizacoes agora.",
        detail: error.message,
        buttons: ["OK"],
        noLink: true
      });
    }
    return { ok: false, reason: error.message };
  }
}

function installDownloadedUpdate() {
  if (!downloaded) return false;
  autoUpdater.quitAndInstall(false, true);
  return true;
}

module.exports = Object.freeze({ initializeUpdater, checkForUpdates, installDownloadedUpdate, MIN_CHECK_INTERVAL_MS });
