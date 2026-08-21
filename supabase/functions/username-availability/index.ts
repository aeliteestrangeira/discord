import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

const ALLOWED_ORIGIN = "https://aeliteestrangeira.github.io";
const USERNAME_RE = /^[a-z0-9_.]{2,32}$/;

function cors(origin: string | null) {
  const allowed = origin === ALLOWED_ORIGIN;
  return {
    "Access-Control-Allow-Origin": allowed ? ALLOWED_ORIGIN : "",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Vary": "Origin",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  };
}

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin");
  const headers = cors(origin);
  if (req.method === "OPTIONS") {
    if (origin !== ALLOWED_ORIGIN) return new Response(null, { status: 403, headers });
    return new Response(null, { status: 204, headers });
  }
  if (req.method !== "POST") {
    return Response.json({ ok: false, error: { code: "method_not_allowed" } }, { status: 405, headers });
  }
  if (origin !== ALLOWED_ORIGIN) {
    return Response.json({ ok: false, error: { code: "origin_not_allowed" } }, { status: 403, headers });
  }

  let payload: Record<string, unknown> = {};
  try {
    payload = await req.json();
  } catch (_) {
    // The validation below returns the same controlled response for malformed JSON.
  }
  const username = String(payload.username ?? "").trim().toLowerCase();
  if (!USERNAME_RE.test(username) || username.includes("..")) {
    return Response.json({
      ok: false,
      error: { code: "username_invalid", message: "Nome de usuário inválido." },
    }, { status: 400, headers });
  }

  const url = Deno.env.get("SUPABASE_URL") ?? "";
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!url || !serviceRole) {
    return Response.json({ ok: false, error: { code: "not_configured" } }, { status: 503, headers });
  }
  const admin = createClient(url, serviceRole, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await admin
    .from("profiles")
    .select("id")
    .ilike("username", username)
    .limit(1);
  if (error) {
    return Response.json({
      ok: false,
      error: { code: "lookup_unavailable", message: "Não foi possível verificar o nome de usuário agora." },
    }, { status: 503, headers });
  }
  return Response.json({ ok: true, available: !data?.length }, {
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8" },
  });
});
