"use strict";

const { shell } = require("electron");
const { APP_ORIGIN } = require("./constants.cjs");

const EXTERNAL_ORIGINS = new Set([
  "https://discord.com",
  "https://support.discord.com",
  "https://hcaptcha.com",
  "https://www.hcaptcha.com",
  "https://accounts.google.com",
  "https://console.cloud.google.com",
  "https://supabase.com"
]);

function parseUrl(value) {
  try { return new URL(value); } catch (_) { return null; }
}

function isAppUrl(value) {
  const parsed = parseUrl(value);
  return Boolean(parsed && parsed.origin === APP_ORIGIN);
}

function isAllowedExternal(value) {
  const parsed = parseUrl(value);
  return Boolean(parsed && parsed.protocol === "https:" && EXTERNAL_ORIGINS.has(parsed.origin));
}

async function openExternalIfAllowed(value) {
  if (!isAllowedExternal(value)) return false;
  await shell.openExternal(value, { activate: true });
  return true;
}

function hardenWebContents(contents) {
  contents.setWindowOpenHandler(({ url }) => {
    if (!isAppUrl(url)) {
      void openExternalIfAllowed(url);
    }
    return { action: "deny" };
  });

  contents.on("will-navigate", (event, detailsOrUrl) => {
    const target = typeof detailsOrUrl === "string" ? detailsOrUrl : detailsOrUrl?.url;
    if (!target || isAppUrl(target)) return;
    event.preventDefault();
    void openExternalIfAllowed(target);
  });
}

function installPermissionPolicy(session) {
  session.setPermissionCheckHandler((_webContents, permission, requestingOrigin, details = {}) => {
    if (permission !== "media") return false;
    if (requestingOrigin !== APP_ORIGIN) return false;
    return details.mediaType === "audio";
  });

  session.setPermissionRequestHandler((webContents, permission, callback, details = {}) => {
    const requestingUrl = details.requestingUrl || webContents?.getURL?.() || "";
    if (permission !== "media" || !isAppUrl(requestingUrl)) {
      callback(false);
      return;
    }
    const mediaTypes = Array.isArray(details.mediaTypes) ? details.mediaTypes : [];
    const audioOnly = mediaTypes.length > 0 && mediaTypes.every((type) => type === "audio");
    callback(audioOnly);
  });

  session.setDevicePermissionHandler(() => false);
}

module.exports = Object.freeze({
  hardenWebContents,
  installPermissionPolicy,
  isAppUrl,
  isAllowedExternal
});
