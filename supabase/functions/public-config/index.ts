import "jsr:@supabase/functions-js/edge-runtime.d.ts";

const ALLOWED_ORIGIN = "https://aeliteestrangeira.github.io";
const SUPABASE_URL = "https://kwekrdluscriubyfolri.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_kRPTrvZZfc2kQlYpF-Q9CA_88jZ9YDT";
const HCAPTCHA_SITEKEY = "63ae6c06-5594-4e42-b542-2c7ee3e437f8";

function cors(origin: string | null) {
  const allowed = origin === ALLOWED_ORIGIN;
  return {
    "Access-Control-Allow-Origin": allowed ? ALLOWED_ORIGIN : "",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Vary": "Origin",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  };
}

Deno.serve((req: Request) => {
  const origin = req.headers.get("origin");
  const headers = cors(origin);

  if (req.method === "OPTIONS") {
    if (origin !== ALLOWED_ORIGIN) return new Response(null, { status: 403, headers });
    return new Response(null, { status: 204, headers });
  }
  if (req.method !== "GET") {
    return Response.json({ ok: false, error: "method_not_allowed" }, { status: 405, headers });
  }
  if (origin && origin !== ALLOWED_ORIGIN) {
    return Response.json({ ok: false, error: "origin_not_allowed" }, { status: 403, headers });
  }

  return Response.json({
    ok: true,
    mode: "web-cloud",
    frontendOrigin: ALLOWED_ORIGIN,
    appBasePath: "/discord/",
    adminPath: "/discord/admin/",
    supabaseUrl: SUPABASE_URL,
    publishableKey: SUPABASE_PUBLISHABLE_KEY,
    hcaptcha: {
      configured: true,
      sitekey: HCAPTCHA_SITEKEY,
      hostname: "aeliteestrangeira.github.io",
    },
  }, { headers: { ...headers, "Content-Type": "application/json; charset=utf-8" } });
});
