"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { setTimeout: sleep } = require("node:timers/promises");
const { APP_PORT, HEALTH_URL } = require("./constants.cjs");

const ROOT = path.resolve(__dirname, "..");
const RUNTIME = path.join(ROOT, ".runtime");
const LOG = path.join(RUNTIME, "desktop.log");
const PYTHON = path.join(ROOT, ".venv", "Scripts", "python.exe");

function ensureRuntimeDir() {
  fs.mkdirSync(RUNTIME, { recursive: true });
}

function log(line) {
  ensureRuntimeDir();
  const text = `${new Date().toISOString()} ${line}\n`;
  fs.appendFileSync(LOG, text, { encoding: "utf8" });
}

function run(command, args, { timeoutMs = 0, phase = command } = {}) {
  return new Promise((resolve, reject) => {
    log(`[${phase}] start: ${command} ${args.join(" ")}`);
    const child = spawn(command, args, {
      cwd: ROOT,
      windowsHide: true,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env }
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });

    let timer = null;
    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        try { child.kill(); } catch (_) {}
        reject(new Error(`${phase}: timeout apos ${timeoutMs} ms.`));
      }, timeoutMs);
    }

    child.once("error", (error) => {
      if (timer) clearTimeout(timer);
      log(`[${phase}] spawn-error: ${error.message}`);
      reject(error);
    });

    child.once("exit", (code, signal) => {
      if (timer) clearTimeout(timer);
      if (stdout.trim()) log(`[${phase}] stdout: ${stdout.trim()}`);
      if (stderr.trim()) log(`[${phase}] stderr: ${stderr.trim()}`);
      if (code === 0) {
        log(`[${phase}] ok`);
        resolve({ stdout, stderr });
        return;
      }
      reject(new Error(`${phase} falhou (codigo=${code}, signal=${signal || "none"}).`));
    });
  });
}

function powershell(scriptRelativePath, extraArgs = [], phase = scriptRelativePath) {
  const script = path.join(ROOT, scriptRelativePath);
  return run(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, ...extraArgs],
    { phase }
  );
}

async function ensurePythonEnvironment() {
  if (fs.existsSync(PYTHON)) return;
  await run("cmd.exe", ["/d", "/s", "/c", "call INSTALL_DEPENDENCIES.bat"], {
    phase: "python-dependencies"
  });
  if (!fs.existsSync(PYTHON)) {
    throw new Error("O ambiente Python nao foi criado por INSTALL_DEPENDENCIES.bat.");
  }
}

async function prepareLocalRuntime() {
  if (process.platform !== "win32") {
    throw new Error("Esta fase desktop suporta Windows somente.");
  }
  ensureRuntimeDir();
  log("desktop bootstrap begin");
  await ensurePythonEnvironment();
  await powershell("priv/scripts/ensure_local_hostname.ps1", [], "hostname");
  await powershell("priv/scripts/harden_instance.ps1", [], "instance-acl");
  await powershell("priv/scripts/ensure_local_tls.ps1", [], "local-tls");
  await powershell(
    "priv/scripts/restart_server.ps1",
    ["-Port", String(APP_PORT), "-NoBrowser"],
    "flask-restart"
  );
}

async function waitForBackend(fetchFn, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 2500);
    try {
      const response = await fetchFn(HEALTH_URL, {
        method: "GET",
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
        headers: { Accept: "application/json" }
      });
      clearTimeout(timer);
      if (response.ok) {
        const body = await response.json().catch(() => ({}));
        if (body && body.ok === true && body.service === "discord-local") {
          log("backend health confirmed");
          return;
        }
      }
      lastError = new Error(`Health check HTTP ${response.status}.`);
    } catch (error) {
      clearTimeout(timer);
      lastError = error;
    }
    await sleep(350);
  }
  throw new Error(`Backend nao ficou pronto em ${timeoutMs} ms: ${lastError?.message || "sem resposta"}`);
}

async function stopBackend() {
  if (process.platform !== "win32") return;
  try {
    await powershell("priv/scripts/stop_server.ps1", [], "flask-stop");
  } catch (error) {
    log(`[flask-stop] non-fatal: ${error.message}`);
  }
}

module.exports = Object.freeze({
  ROOT,
  LOG,
  prepareLocalRuntime,
  waitForBackend,
  stopBackend,
  log
});
