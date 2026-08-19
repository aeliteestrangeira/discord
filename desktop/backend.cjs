"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { setTimeout: sleep } = require("node:timers/promises");
const { APP_PORT, HEALTH_URL } = require("./constants.cjs");

const SOURCE_ROOT = path.resolve(__dirname, "..");
let runtimeRoot = path.join(SOURCE_ROOT, ".runtime");
let logPath = path.join(runtimeRoot, "desktop.log");
let packagedBackend = null;

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function setLogRoot(dir) {
  runtimeRoot = dir;
  ensureDir(runtimeRoot);
  logPath = path.join(runtimeRoot, "desktop.log");
}

function log(line) {
  ensureDir(runtimeRoot);
  fs.appendFileSync(logPath, `${new Date().toISOString()} ${line}\n`, { encoding: "utf8" });
}

function run(command, args, { timeoutMs = 0, phase = command, cwd = process.cwd(), env = process.env } = {}) {
  return new Promise((resolve, reject) => {
    let effectiveCwd;
    try {
      effectiveCwd = path.resolve(cwd || process.cwd());
      if (!fs.statSync(effectiveCwd).isDirectory()) {
        throw new Error("nao e um diretorio");
      }
    } catch (_) {
      const error = new Error(`${phase}: diretorio de trabalho invalido: ${cwd || "(vazio)"}`);
      log(`[${phase}] cwd-error: ${error.message}`);
      reject(error);
      return;
    }
    log(`[${phase}] start cwd=${effectiveCwd}: ${command} ${args.join(" ")}`);
    const child = spawn(command, args, {
      cwd: effectiveCwd,
      windowsHide: true,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ...env }
    });

    let stdout = "";
    let stderr = "";
    child.stdout?.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr?.on("data", (chunk) => { stderr += chunk.toString("utf8"); });

    let timer = null;
    let settled = false;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (error) reject(error); else resolve(result);
    };

    if (timeoutMs > 0) {
      timer = setTimeout(() => {
        try { child.kill(); } catch (_) {}
        finish(new Error(`${phase}: timeout apos ${timeoutMs} ms.`));
      }, timeoutMs);
    }

    child.once("error", (error) => {
      log(`[${phase}] spawn-error: ${error.message}`);
      finish(error);
    });

    child.once("exit", (code, signal) => {
      if (stdout.trim()) log(`[${phase}] stdout: ${stdout.trim()}`);
      if (stderr.trim()) log(`[${phase}] stderr: ${stderr.trim()}`);
      if (code === 0) {
        log(`[${phase}] ok`);
        finish(null, { stdout, stderr });
        return;
      }
      finish(new Error(`${phase} falhou (codigo=${code}, signal=${signal || "none"}).`));
    });
  });
}

function existingFile(candidate) {
  try {
    return fs.statSync(candidate).isFile();
  } catch (_) {
    return false;
  }
}

function windowsRoot(env = process.env) {
  return env.SystemRoot || env.WINDIR || "C:\\Windows";
}

function resolveSystem32Executable(name, env = process.env) {
  const candidate = path.join(windowsRoot(env), "System32", name);
  if (!existingFile(candidate)) {
    throw new Error(`Executavel confiavel do Windows nao encontrado: ${candidate}`);
  }
  return candidate;
}

function resolveWindowsPowerShell(env = process.env) {
  const candidates = [
    path.join(windowsRoot(env), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
  ];
  const programFiles = env.ProgramFiles;
  if (programFiles) candidates.push(path.join(programFiles, "PowerShell", "7", "pwsh.exe"));
  for (const candidate of candidates) {
    if (existingFile(candidate)) return candidate;
  }
  throw new Error(`PowerShell confiavel nao encontrado nos caminhos do sistema: ${candidates.join(", ")}`);
}

function powershell(script, extraArgs = [], phase = path.basename(script), options = {}) {
  const effectiveEnv = { ...process.env, ...(options.env || {}) };
  const executable = resolveWindowsPowerShell(effectiveEnv);
  return run(
    executable,
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, ...extraArgs],
    { phase, ...options }
  );
}

function devPython() {
  return path.join(SOURCE_ROOT, ".venv", "Scripts", "python.exe");
}

async function ensurePythonEnvironment() {
  const python = devPython();
  if (fs.existsSync(python)) return;
  await run(resolveSystem32Executable("cmd.exe"), ["/d", "/s", "/c", "call INSTALL_DEPENDENCIES.bat"], {
    phase: "python-dependencies",
    cwd: SOURCE_ROOT
  });
  if (!fs.existsSync(python)) {
    throw new Error("O ambiente Python nao foi criado por INSTALL_DEPENDENCIES.bat.");
  }
}

function dataPaths(dataRoot) {
  const instance = path.join(dataRoot, "instance");
  const runtime = path.join(dataRoot, "runtime");
  const config = path.join(dataRoot, "config");
  return Object.freeze({
    root: dataRoot,
    instance,
    runtime,
    config,
    privateEnv: path.join(config, "SUPABASE_PRIVILEGED.env"),
    tlsDir: path.join(instance, "tls"),
    ca: path.join(instance, "tls", "local-ca.cer"),
    cert: path.join(instance, "tls", "server-cert.pem"),
    key: path.join(instance, "tls", "server-key.pem")
  });
}

function ensureDataTree(paths) {
  for (const dir of [paths.root, paths.instance, paths.runtime, paths.config, paths.tlsDir]) ensureDir(dir);
}

function privateBootstrapPresent(paths) {
  return fs.existsSync(paths.privateEnv) && fs.statSync(paths.privateEnv).isFile();
}

function importPrivateBootstrap(sourceFile, paths) {
  if (!sourceFile) return false;
  const source = path.resolve(sourceFile);
  if (!fs.existsSync(source) || !fs.statSync(source).isFile()) {
    throw new Error("Arquivo privado selecionado nao existe.");
  }
  ensureDir(paths.config);
  if (fs.existsSync(paths.privateEnv)) {
    throw new Error("O bootstrap privado persistente ja existe e nao sera sobrescrito automaticamente.");
  }
  fs.copyFileSync(source, paths.privateEnv, fs.constants.COPYFILE_EXCL);
  log(`private bootstrap imported from explicit user selection: ${path.basename(source)}`);
  return true;
}

function packagedEnv(paths) {
  return {
    APP_HOSTNAME: "discord",
    FLASK_BIND: "127.0.0.1",
    FLASK_PORT: String(APP_PORT),
    DISCORD_INSTANCE_DIR: paths.instance,
    DISCORD_RUNTIME_DIR: paths.runtime,
    DISCORD_PRIVATE_CONFIG_DIR: paths.config,
    DISCORD_PRIVATE_ENV_FILE: paths.privateEnv,
    DISCORD_DESKTOP_PACKAGED: "1"
  };
}

async function prepareSourceRuntime() {
  setLogRoot(path.join(SOURCE_ROOT, ".runtime"));
  log("desktop bootstrap begin mode=source");
  await ensurePythonEnvironment();
  await powershell(path.join(SOURCE_ROOT, "priv", "scripts", "ensure_local_hostname.ps1"), [], "hostname", { cwd: SOURCE_ROOT });
  await powershell(path.join(SOURCE_ROOT, "priv", "scripts", "harden_instance.ps1"), [], "instance-acl", { cwd: SOURCE_ROOT });
  await powershell(path.join(SOURCE_ROOT, "priv", "scripts", "ensure_local_tls.ps1"), [], "local-tls", { cwd: SOURCE_ROOT });
  await powershell(
    path.join(SOURCE_ROOT, "priv", "scripts", "restart_server.ps1"),
    ["-Port", String(APP_PORT), "-NoBrowser"],
    "flask-restart",
    { cwd: SOURCE_ROOT }
  );
  return { mode: "source", paths: dataPaths(SOURCE_ROOT) };
}

function spawnPackagedBackend(executable, args, env, cwd) {
  const child = spawn(executable, args, {
    cwd,
    windowsHide: true,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, ...env }
  });
  child.stdout?.on("data", (chunk) => log(`[backend] stdout: ${chunk.toString("utf8").trimEnd()}`));
  child.stderr?.on("data", (chunk) => log(`[backend] stderr: ${chunk.toString("utf8").trimEnd()}`));
  child.once("error", (error) => log(`[backend] spawn-error: ${error.message}`));
  child.once("exit", (code, signal) => log(`[backend] exit code=${code} signal=${signal || "none"}`));
  return child;
}

async function preparePackagedRuntime({ resourcesPath, dataRoot }) {
  const paths = dataPaths(dataRoot);
  ensureDataTree(paths);
  setLogRoot(paths.runtime);
  log("desktop bootstrap begin mode=packaged");

  const runtimeDir = path.join(resourcesPath, "runtime");
  const backendDir = path.join(resourcesPath, "backend");
  const hostnameScript = path.join(runtimeDir, "ensure_local_hostname.ps1");
  const setupScript = path.join(runtimeDir, "packaged_setup.ps1");
  const tlsExe = path.join(backendDir, "discord-tls.exe");
  const backendExe = path.join(backendDir, "discord-backend.exe");
  for (const required of [hostnameScript, setupScript, tlsExe, backendExe]) {
    if (!fs.existsSync(required)) throw new Error(`Recurso do instalador ausente: ${required}`);
  }

  const env = packagedEnv(paths);
  await powershell(hostnameScript, ["-LogPath", path.join(paths.runtime, "hostname-setup.log")], "hostname", { env, cwd: dataRoot });
  await run(tlsExe, [], { phase: "local-tls-generate", cwd: dataRoot, env, timeoutMs: 30000 });
  await powershell(setupScript, ["-DataRoot", dataRoot, "-CaPath", paths.ca], "desktop-data-acl-and-trust", { env, cwd: dataRoot });

  if (packagedBackend && !packagedBackend.killed) {
    try { packagedBackend.kill(); } catch (_) {}
  }
  const marker = `${Date.now()}-${process.pid}-${Math.random().toString(16).slice(2)}`;
  packagedBackend = spawnPackagedBackend(
    backendExe,
    ["--bind", "127.0.0.1", "--port", String(APP_PORT), "--tls-cert", paths.cert, "--tls-key", paths.key, "--instance-marker", marker],
    env,
    dataRoot
  );
  return { mode: "packaged", paths };
}

async function prepareLocalRuntime(options = {}) {
  if (process.platform !== "win32") {
    throw new Error("Esta fase desktop suporta Windows somente.");
  }
  if (options.packaged) {
    if (!options.resourcesPath || !options.dataRoot) throw new Error("Desktop empacotado sem resourcesPath/dataRoot.");
    return preparePackagedRuntime(options);
  }
  return prepareSourceRuntime();
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

async function stopBackend({ packaged = false } = {}) {
  if (process.platform !== "win32") return;
  if (packaged) {
    const child = packagedBackend;
    packagedBackend = null;
    if (!child || child.killed) return;
    try { child.kill(); } catch (error) { log(`[backend-stop] non-fatal: ${error.message}`); }
    return;
  }
  try {
    await powershell(path.join(SOURCE_ROOT, "priv", "scripts", "stop_server.ps1"), [], "flask-stop", { cwd: SOURCE_ROOT });
  } catch (error) {
    log(`[flask-stop] non-fatal: ${error.message}`);
  }
}

module.exports = Object.freeze({
  SOURCE_ROOT,
  get LOG() { return logPath; },
  dataPaths,
  privateBootstrapPresent,
  importPrivateBootstrap,
  prepareLocalRuntime,
  waitForBackend,
  stopBackend,
  log
});
