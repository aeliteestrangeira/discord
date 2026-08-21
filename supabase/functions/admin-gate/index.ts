import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2.112.3";

const ALLOWED_ORIGIN = "https://aeliteestrangeira.github.io";

function cors(origin: string | null) {
  return {
    "Access-Control-Allow-Origin": origin === ALLOWED_ORIGIN ? ALLOWED_ORIGIN : "",
    "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Vary": "Origin",
    "X-Content-Type-Options": "nosniff",
  };
}

function json(body: Record<string, unknown>, status: number, headers: Record<string, string>) {
  return Response.json(body, { status, headers });
}

Deno.serve(async (req: Request) => {
  const origin = req.headers.get("origin");
  const headers = cors(origin);
  if (req.method === "OPTIONS") {
    if (origin !== ALLOWED_ORIGIN) return new Response(null, { status: 403, headers });
    return new Response(null, { status: 204, headers });
  }
  if (req.method !== "GET") return json({ ok: false, error: "method_not_allowed" }, 405, headers);
  if (origin && origin !== ALLOWED_ORIGIN) {
    return json({ ok: false, error: "origin_not_allowed" }, 403, headers);
  }

  const authorization = req.headers.get("authorization") ?? "";
  const token = authorization.toLowerCase().startsWith("bearer ")
    ? authorization.slice(7).trim()
    : "";
  if (!token) return json({ ok: false, admin: false, error: "missing_token" }, 401, headers);

  const supabaseUrl = Deno.env.get("SUPABASE_URL") ?? "";
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
  if (!supabaseUrl || !anonKey || !serviceRole) {
    return json({ ok: false, admin: false, error: "server_not_configured" }, 503, headers);
  }

  const verifier = createClient(supabaseUrl, anonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: verified, error: verifyError } = await verifier.auth.getUser(token);
  const userId = verified?.user?.id ?? "";
  if (verifyError || !userId) {
    return json({ ok: false, admin: false, error: "invalid_token" }, 401, headers);
  }

  const adminClient = createClient(supabaseUrl, serviceRole, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data: authorizationRows, error: authorizationError } = await adminClient
    .rpc("web_admin_authorization", { p_user_id: userId });
  if (authorizationError) {
    console.error("admin-gate authorization lookup failed", authorizationError.code);
    return json({ ok: false, admin: false, error: "admin_lookup_failed" }, 503, headers);
  }
  const authorizationRow = Array.isArray(authorizationRows) ? authorizationRows[0] : authorizationRows;
  if (authorizationRow?.enabled !== true) {
    return json({ ok: true, admin: false, adminEligible: false, mfaRequired: false }, 403, headers);
  }

  const { data: assurance, error: assuranceError } =
    await verifier.auth.mfa.getAuthenticatorAssuranceLevel(token);
  if (assuranceError) {
    return json({ ok: false, admin: false, adminEligible: true, error: "aal_lookup_failed" }, 401, headers);
  }
  const aal = assurance?.currentLevel ?? "aal1";
  if (aal !== "aal2") {
    return json({ ok: true, admin: false, adminEligible: true, mfaRequired: true, aal }, 403, headers);
  }

  const [{ data: authData, error: usersError }, { data: profiles }] =
    await Promise.all([
      adminClient.auth.admin.listUsers({ page: 1, perPage: 100 }),
      adminClient.from("profiles").select("id,username"),
    ]);
  if (usersError) {
    console.error("admin-gate user listing failed", usersError.code);
    return json({ ok: false, admin: false, adminEligible: true, error: "admin_data_failed" }, 503, headers);
  }

  const usernames = new Map((profiles ?? []).map((profile) => [profile.id, profile.username ?? ""]));
  const users = (authData?.users ?? []).map((user) => ({
    id: user.id,
    email: user.email ?? "",
    username: usernames.get(user.id) ?? "",
    emailConfirmed: Boolean(user.email_confirmed_at),
    createdAt: user.created_at,
    lastSignInAt: user.last_sign_in_at ?? null,
  }));

  return json({
    ok: true,
    admin: true,
    adminEligible: true,
    mfaRequired: false,
    aal,
    user: { id: userId, email: verified.user?.email ?? "" },
    metrics: {
      authUsers: users.length,
      confirmedEmails: users.filter((user) => user.emailConfirmed).length,
      enabledAdmins: Number(authorizationRow.enabled_admins ?? 0),
    },
    users,
  }, 200, headers);
});
