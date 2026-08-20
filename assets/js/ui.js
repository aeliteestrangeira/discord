(() => {
  "use strict";
  const currentScript = document.currentScript;
  const appRoot = new URL("./", currentScript?.src || location.href);
  const rootPath = appRoot.pathname.endsWith("/") ? appRoot.pathname : `${appRoot.pathname}/`;
  const pathname = location.pathname.toLowerCase();
  const basePath = rootPath.toLowerCase();
  const relativePath = pathname.startsWith(basePath) ? `/${pathname.slice(basePath.length)}` : pathname;
  const auth = new Set(["/", "/login", "/login.html", "/register.html"]);
  if (auth.has(relativePath)) {
    const sensitive = new Set(["email", "password", "identifier", "username", "global_name", "phone", "token", "access_token", "refresh_token", "hcaptchatoken", "h-captcha-response"]);
    const url = new URL(location.href);
    let changed = false;
    for (const key of [...url.searchParams.keys()]) if (sensitive.has(key.toLowerCase())) { url.searchParams.delete(key); changed = true; }
    if (changed) history.replaceState(history.state, "", `${url.pathname}${url.search}${url.hash}`);
    document.addEventListener("submit", (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !form.querySelector('input[type="password"]')) return;
      const method = String(form.getAttribute("method") || "get").toLowerCase();
      if (method === "get") event.preventDefault();
    }, true);
  }
  import(new URL("ui/bootstrap.js", appRoot).href)
    .then(({ boot }) => boot())
    .catch((error) => {
      console.error("Falha ao inicializar a camada de interface.", error);
      document.dispatchEvent(new CustomEvent("app:bootstrap-error", { detail: { error } }));
    });
})();
