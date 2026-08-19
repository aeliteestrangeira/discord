"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", Object.freeze({
  runtime: "electron",
  platform: process.platform,
  version: () => ipcRenderer.invoke("desktop:version"),
  checkForUpdates: () => ipcRenderer.invoke("desktop:check-for-updates"),
  installUpdate: () => ipcRenderer.invoke("desktop:install-update")
}));
