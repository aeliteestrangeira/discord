"use strict";

const APP_HOST = "discord";
const APP_PORT = Number.parseInt(process.env.DISCORD_DESKTOP_PORT || "8000", 10);
if (!Number.isInteger(APP_PORT) || APP_PORT < 1024 || APP_PORT > 65535) {
  throw new Error("DISCORD_DESKTOP_PORT invalida.");
}

const APP_ORIGIN = `https://${APP_HOST}:${APP_PORT}`;
const APP_URL = `${APP_ORIGIN}/`;
const HEALTH_URL = `${APP_ORIGIN}/api/desktop/health`;

module.exports = Object.freeze({ APP_HOST, APP_PORT, APP_ORIGIN, APP_URL, HEALTH_URL });
