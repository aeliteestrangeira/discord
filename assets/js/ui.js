(() => {
  "use strict";
  const auth = new Set(["/", "/login", "/login.html", "/register.html"]);
  if (auth.has(location.pathname.toLowerCase())) {
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
  import("/ui/bootstrap.js")
    .then(({ boot }) => boot())
    .catch((error) => {
      console.error("Falha ao inicializar a camada de interface.", error);
      document.dispatchEvent(new CustomEvent("app:bootstrap-error", { detail: { error } }));
    });
})();
