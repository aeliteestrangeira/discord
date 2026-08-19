from __future__ import annotations

import base64
from contextlib import contextmanager
from queue import Empty, Full, LifoQueue
import hashlib
import hmac
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

from supabase import create_client

from .storage import ControlStore


class ProviderError(RuntimeError):
    def __init__(self, public_message: str, code: str = "provider_error", internal: str = ""):
        super().__init__(public_message)
        self.public_message = public_message
        self.code = code
        self.internal = internal


class SupabaseService:
    def __init__(self, store: ControlStore, root: Path):
        self.store = store
        self.root = root
        self._env_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        self._env_publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        self._env_project_ref = os.getenv("SUPABASE_PROJECT_REF", "").strip()
        self._env_db_host = os.getenv("SUPABASE_DB_HOST", "").strip()
        self._registration_schema_cache: Optional[dict[str, Any]] = None
        self._registration_schema_cache_until = 0.0
        self._auth_settings_cache: Optional[dict[str, Any]] = None
        self._auth_settings_cache_until = 0.0
        # Small in-process PostgreSQL connection pool. The previous code opened
        # a brand-new TLS/PostgreSQL connection for every query (including the
        # session watchdog), which dominated latency in the local application.
        # Queue entries carry their DSN so runtime configuration changes cannot
        # accidentally reuse a connection to an older project.
        self._db_pool: LifoQueue[tuple[str, Any]] = LifoQueue(maxsize=4)

    @property
    def url(self) -> str:
        return (self.store.get_secret("SUPABASE_URL") or self._env_url).strip().rstrip("/")

    @property
    def publishable_key(self) -> str:
        return (self.store.get_secret("SUPABASE_PUBLISHABLE_KEY") or self._env_publishable_key).strip()

    @property
    def project_ref(self) -> str:
        return (self.store.get_secret("SUPABASE_PROJECT_REF") or self._env_project_ref).strip()

    @property
    def db_host(self) -> str:
        return (self.store.get_secret("SUPABASE_DB_HOST") or self._env_db_host).strip()

    @property
    def public_configured(self) -> bool:
        return bool(self.url and self.publishable_key)

    @property
    def secret_key(self) -> str:
        return (self.store.get_secret("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SECRET_KEY", "")).strip()

    @property
    def service_role_key(self) -> str:
        return (self.store.get_secret("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")).strip()

    @property
    def legacy_anon_key(self) -> str:
        return (self.store.get_secret("SUPABASE_LEGACY_ANON_KEY") or os.getenv("SUPABASE_LEGACY_ANON_KEY", "")).strip()

    @property
    def legacy_jwt_secret(self) -> str:
        return (self.store.get_secret("SUPABASE_JWT_LEGACY_SECRET") or os.getenv("SUPABASE_JWT_LEGACY_SECRET", "")).strip()

    @property
    def jwks_url(self) -> str:
        configured = (self.store.get_secret("SUPABASE_JWKS_URL") or os.getenv("SUPABASE_JWKS_URL", "")).strip()
        return configured or (f"{self.url}/auth/v1/.well-known/jwks.json" if self.url else "")

    @property
    def jwks_kid(self) -> str:
        return (self.store.get_secret("SUPABASE_JWKS_KID") or os.getenv("SUPABASE_JWKS_KID", "")).strip()

    @property
    def jwks_previous_kid(self) -> str:
        return (self.store.get_secret("SUPABASE_JWKS_PREVIOUS_KID") or os.getenv("SUPABASE_JWKS_PREVIOUS_KID", "")).strip()

    @property
    def jwks_static_json(self) -> str:
        return (self.store.get_secret("SUPABASE_JWKS_STATIC_JSON") or os.getenv("SUPABASE_JWKS_STATIC_JSON", "")).strip()

    def validate_static_jwks(self) -> tuple[bool, str]:
        """Validate owner-supplied public JWKS metadata without a network request."""
        if not self.jwks_static_json:
            return False, "JWKS estático ausente."
        try:
            body = json.loads(self.jwks_static_json)
            keys = body.get("keys") if isinstance(body, dict) else None
            if not isinstance(keys, list) or not keys:
                return False, "JWKS estático sem chaves."
            if self.jwks_kid:
                key = next((item for item in keys if isinstance(item, dict) and item.get("kid") == self.jwks_kid), None)
                if not key:
                    return False, "KID atual não encontrado no JWKS estático."
                if key.get("alg") != "ES256" or key.get("kty") != "EC" or key.get("crv") != "P-256":
                    return False, "Parâmetros da chave atual não correspondem a ES256/P-256."
                if not key.get("x") or not key.get("y"):
                    return False, "Coordenadas da chave EC ausentes."
            return True, f"JWKS estático válido ({len(keys)} chave(s))."
        except Exception as exc:
            return False, exc.__class__.__name__

    @property
    def admin_key(self) -> str:
        # Prefer the modern sb_secret_* key when configured. The legacy
        # service_role JWT remains a server-side fallback for this project.
        return self.secret_key or self.service_role_key

    @property
    def admin_key_kind(self) -> str:
        if self.secret_key:
            return "secret"
        if self.service_role_key:
            return "service_role_legacy"
        return "none"

    @property
    def db_password(self) -> str:
        return (self.store.get_secret("SUPABASE_DB_PASSWORD") or os.getenv("SUPABASE_DB_PASSWORD", "")).strip()

    @property
    def admin_configured(self) -> bool:
        return bool(self.url and self.admin_key)

    @property
    def database_configured(self) -> bool:
        return bool(self.db_host and self.db_password and self.project_ref)

    @contextmanager
    def _database_connection(self, *, connect_timeout: int = 8):
        """Reuse a bounded set of PostgreSQL connections with transaction hygiene.

        This preserves the old ``with psycopg.connect(...)`` semantics: successful
        operations commit and failures roll back. Idle connections are then reused
        instead of repeating DNS/TCP/TLS/PostgreSQL authentication on every request.
        """
        if not self.database_configured:
            raise ProviderError("Banco de dados não configurado.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc

        dsn = self.db_dsn()
        conn = None
        while conn is None:
            try:
                pooled_dsn, candidate = self._db_pool.get_nowait()
            except Empty:
                break
            if pooled_dsn == dsn and not bool(getattr(candidate, "closed", True)):
                conn = candidate
            else:
                try:
                    candidate.close()
                except Exception:
                    pass

        if conn is None:
            conn = psycopg.connect(dsn, connect_timeout=max(1, int(connect_timeout)))

        reusable = True
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                reusable = False
            raise
        finally:
            if bool(getattr(conn, "closed", True)):
                reusable = False
            if reusable:
                try:
                    self._db_pool.put_nowait((dsn, conn))
                except Full:
                    try:
                        conn.close()
                    except Exception:
                        pass
            else:
                try:
                    conn.close()
                except Exception:
                    pass

    def _public_client(self):
        if not self.public_configured:
            raise ProviderError("Provedor de autenticação não configurado.", "not_configured")
        return create_client(self.url, self.publishable_key)

    def _admin_client(self):
        if not self.admin_configured:
            raise ProviderError("Operação administrativa negada: chave secreta não configurada.", "admin_key_missing")
        return create_client(self.url, self.admin_key)

    @staticmethod
    def _error_code(exc: Exception) -> str:
        code = str(getattr(exc, "code", "") or "").strip()
        if code:
            return code
        detail = str(exc or "").lower()
        if "email signups are disabled" in detail or "email signup is disabled" in detail:
            return "email_provider_disabled"
        if "signups are disabled" in detail or "signup is disabled" in detail:
            return "signup_disabled"
        return str(getattr(exc, "status", "") or exc.__class__.__name__)

    @staticmethod
    def _extract_auth_response(response: Any) -> dict[str, Any]:
        user = getattr(response, "user", None)
        session = getattr(response, "session", None)
        metadata = getattr(user, "user_metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        # Confirmation state is independent from whether Auth returned a session.
        # This matters for projects that may allow unverified-email sign-in: such
        # a user can have a valid provider session while still needing the local
        # application to keep them in the restricted ``pending`` role.
        email_confirmed = bool(
            getattr(user, "email_confirmed_at", None)
            or getattr(user, "confirmed_at", None)
        )
        return {
            "user_id": str(getattr(user, "id", "") or ""),
            "email": str(getattr(user, "email", "") or ""),
            "phone": str(getattr(user, "phone", "") or ""),
            "username": str(metadata.get("username") or "").strip().lower(),
            "global_name": str(metadata.get("global_name") or "").strip(),
            "email_confirmed": email_confirmed,
            "access_token": getattr(session, "access_token", None) if session else None,
            "refresh_token": getattr(session, "refresh_token", None) if session else None,
            "expires_at": getattr(session, "expires_at", None) if session else None,
            "has_session": bool(session),
        }


    def _auth_api_json(self, path: str, payload: dict[str, Any], *, bearer: str | None = None, timeout: int = 10) -> dict[str, Any]:
        if not self.public_configured:
            raise ProviderError("Provedor de autenticação não configurado.", "not_configured")
        headers = {
            "apikey": self.publishable_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "local-auth-proxy/1.0",
        }
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        req = urllib.request.Request(
            f"{self.url}/auth/v1/{path.lstrip('/')}",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            code = str(body.get("code") or body.get("error_code") or body.get("error") or f"http_{exc.code}")
            message = str(body.get("msg") or body.get("message") or "Operação de autenticação recusada.")
            raise ProviderError(message, code, raw[:2000]) from exc
        except Exception as exc:
            raise ProviderError("Serviço de autenticação indisponível.", exc.__class__.__name__, str(exc)) from exc

    def _auth_api_get_json(self, path: str, *, timeout: int = 10) -> dict[str, Any]:
        if not self.public_configured:
            raise ProviderError("Provedor de autenticação não configurado.", "not_configured")
        req = urllib.request.Request(
            f"{self.url}/auth/v1/{path.lstrip('/')}",
            headers={
                "apikey": self.publishable_key,
                "Accept": "application/json",
                "User-Agent": "local-auth-proxy/1.0",
            },
            method="GET",
        )
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw) if raw else {}
                return body if isinstance(body, dict) else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            code = str(body.get("code") or body.get("error_code") or body.get("error") or f"http_{exc.code}")
            message = str(body.get("msg") or body.get("message") or "Operação de autenticação recusada.")
            raise ProviderError(message, code, raw[:2000]) from exc
        except Exception as exc:
            raise ProviderError("Serviço de autenticação indisponível.", exc.__class__.__name__, str(exc)) from exc

    def public_auth_settings(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force and self._auth_settings_cache is not None and now < self._auth_settings_cache_until:
            return dict(self._auth_settings_cache)
        settings = self._auth_api_get_json("settings", timeout=8)
        self._auth_settings_cache = dict(settings)
        self._auth_settings_cache_until = now + 60.0
        return dict(settings)

    def public_signup_disabled(self) -> bool:
        """Return True only when the public Auth settings explicitly disable sign-up.

        Unknown/missing settings do not authorize an administrative fallback; in
        that case the normal public sign-up is attempted and only explicit Auth
        error codes may select the fallback.
        """
        try:
            settings = self.public_auth_settings()
        except ProviderError:
            return False
        return settings.get("disable_signup") is True

    def start_passkey_authentication(self) -> dict[str, Any]:
        return self._auth_api_json("passkeys/authentication/options", {})

    def verify_passkey_authentication(self, challenge_id: str, credential: dict[str, Any]) -> dict[str, Any]:
        body = self._auth_api_json(
            "passkeys/authentication/verify",
            {"challenge_id": challenge_id, "credential": credential},
        )
        user = body.get("user") if isinstance(body.get("user"), dict) else {}
        access_token = str(body.get("access_token") or "")
        refresh_token = str(body.get("refresh_token") or "")
        expires_at = body.get("expires_at")
        if not expires_at and body.get("expires_in"):
            try:
                expires_at = int(time.time()) + int(body.get("expires_in"))
            except (TypeError, ValueError):
                expires_at = None
        metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
        return {
            "user_id": str(user.get("id") or ""),
            "email": str(user.get("email") or ""),
            "phone": str(user.get("phone") or ""),
            "username": str(metadata.get("username") or "").strip().lower(),
            "global_name": str(metadata.get("global_name") or "").strip(),
            "email_confirmed": bool(user.get("email_confirmed_at") or user.get("confirmed_at") or access_token),
            "access_token": access_token or None,
            "refresh_token": refresh_token or None,
            "expires_at": expires_at,
            "has_session": bool(access_token),
            "raw": body,
        }

    def sign_in(self, identifier: str, password: str) -> dict[str, Any]:
        client = self._public_client()
        credentials = {"password": password}
        if "@" in identifier:
            credentials["email"] = identifier
        else:
            credentials["phone"] = identifier
        try:
            response = client.auth.sign_in_with_password(credentials)
            return self._extract_auth_response(response)
        except Exception as exc:
            raise ProviderError("Não foi possível autenticar com as credenciais informadas.", self._error_code(exc), str(exc)) from exc

    def pending_email_identity(self, email: str) -> dict[str, Any]:
        """Resolve an unconfirmed email user after Auth proved the password.

        Supabase Auth intentionally rejects password sign-in with
        ``email_not_confirmed`` *after* it has verified the password and account
        ban state.  The Flask login route uses this lookup only for that exact
        provider error, so this method does not verify credentials itself and
        never reads ``encrypted_password``.  It only resolves the identity needed
        to create a restricted local ``pending`` session with no Supabase access
        or refresh token.
        """
        value = (email or "").strip().lower()
        if not value or "@" not in value or len(value) > 320:
            raise ProviderError("Não foi possível autenticar com as credenciais informadas.", "invalid_credentials")
        if not self.database_configured:
            raise ProviderError(
                "Não foi possível concluir o acesso pendente: conexão de banco não configurada.",
                "db_password_missing",
            )
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc

        sql = """
            SELECT
                u.id::text,
                COALESCE(u.email, ''),
                COALESCE(u.phone, ''),
                (u.email_confirmed_at IS NOT NULL OR u.confirmed_at IS NOT NULL) AS email_confirmed,
                COALESCE(NULLIF(p.username, ''), NULLIF(lower(u.raw_user_meta_data->>'username'), ''), ''),
                COALESCE(NULLIF(p.global_name, ''), NULLIF(u.raw_user_meta_data->>'global_name', ''), '')
            FROM auth.users u
            LEFT JOIN public.profiles p ON p.id = u.id
            WHERE lower(u.email) = lower(%s)
              AND u.deleted_at IS NULL
            LIMIT 1
        """
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (value,))
                    row = cur.fetchone()
        except Exception as exc:
            raise ProviderError(
                "Não foi possível concluir o acesso pendente agora.",
                "pending_identity_lookup_failed",
                str(exc),
            ) from exc

        if not row:
            raise ProviderError("Não foi possível autenticar com as credenciais informadas.", "invalid_credentials")
        return {
            "user_id": str(row[0] or ""),
            "email": str(row[1] or ""),
            "phone": str(row[2] or ""),
            "email_confirmed": bool(row[3]),
            "username": str(row[4] or "").strip().lower(),
            "global_name": str(row[5] or "").strip(),
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
            "has_session": False,
            "verification_kind": "signup",
            "authentication_mode": "local-pending-after-provider-proof",
        }

    def auth_email_exists(self, email: str) -> bool:
        """Return whether an email exists in Supabase Auth.

        This is a read-only server-side lookup against auth.users using the
        configured direct PostgreSQL connection. It is intentionally not
        exposed as a general-purpose public endpoint.
        """
        value = (email or "").strip()
        if not value or len(value) > 320:
            return False
        if not self.database_configured:
            raise ProviderError(
                "Não foi possível verificar a existência da conta: conexão de banco não configurada.",
                "db_password_missing",
            )
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc

        sql = "SELECT EXISTS (SELECT 1 FROM auth.users WHERE lower(email) = lower(%s))"
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (value,))
                    row = cur.fetchone()
                    return bool(row and row[0])
        except Exception as exc:
            raise ProviderError(
                "Não foi possível verificar a existência da conta.",
                "auth_user_lookup_failed",
                str(exc),
            ) from exc

    def request_login_link(self, identifier: str) -> str:
        client = self._public_client()
        value = (identifier or "").strip()
        if not value:
            raise ProviderError("Identificador ausente.", "validation")

        # The login field accepts either email or phone. Supabase passwordless
        # auth supports both. For email it sends a magic link by default; for
        # phone it sends an OTP. should_create_user=False prevents this recovery
        # action from creating a new account.
        if "@" in value:
            credentials: dict[str, Any] = {
                "email": value,
                "options": {"should_create_user": False},
            }
            channel = "email"
        else:
            credentials = {
                "phone": value,
                "options": {"should_create_user": False},
            }
            channel = "phone"
        try:
            client.auth.sign_in_with_otp(credentials)
            return channel
        except Exception as exc:
            raise ProviderError("Não foi possível solicitar o acesso sem senha.", self._error_code(exc), str(exc)) from exc

    def username_exists(self, username: str) -> bool:
        value = (username or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_.]{2,32}", value) or ".." in value:
            raise ProviderError("Nome de usuário inválido.", "username_invalid")
        if not self.database_configured:
            raise ProviderError("Não foi possível verificar o nome de usuário agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    # Auth metadata is the authoritative source during the sign-up
                    # transaction. profiles is also checked so legacy/backfilled
                    # rows remain protected by the same case-insensitive rule.
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                              FROM auth.users
                             WHERE lower(COALESCE(raw_user_meta_data->>'username','')) = lower(%s)
                            UNION ALL
                            SELECT 1
                              FROM public.profiles
                             WHERE username IS NOT NULL AND lower(username) = lower(%s)
                        )
                        """,
                        (value, value),
                    )
                    row = cur.fetchone()
                    return bool(row and row[0])
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Não foi possível verificar o nome de usuário agora.",
                "username_lookup_failed",
                str(exc),
            ) from exc

    def existing_usernames(self, usernames: list[str]) -> set[str]:
        values = sorted({(value or "").strip().lower() for value in usernames if (value or "").strip()})
        if not values:
            return set()
        for value in values:
            if not re.fullmatch(r"[a-z0-9_.]{2,32}", value) or ".." in value:
                raise ProviderError("Nome de usuário inválido.", "username_invalid")
        if not self.database_configured:
            raise ProviderError("Não foi possível verificar o nome de usuário agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    # Check an entire candidate set in one connection/query. This
                    # keeps username suggestions responsive while preserving the
                    # same auth.users + public.profiles authority used by the
                    # single-name lookup.
                    cur.execute(
                        """
                        WITH requested(username) AS (
                            SELECT unnest(%s::text[])
                        )
                        SELECT requested.username
                          FROM requested
                         WHERE EXISTS (
                                   SELECT 1
                                     FROM auth.users
                                    WHERE lower(COALESCE(raw_user_meta_data->>'username','')) = requested.username
                               )
                            OR EXISTS (
                                   SELECT 1
                                     FROM public.profiles
                                    WHERE username IS NOT NULL
                                      AND lower(username) = requested.username
                               )
                        """,
                        (values,),
                    )
                    return {str(row[0]).lower() for row in cur.fetchall() if row and row[0]}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Não foi possível verificar os nomes de usuário agora.",
                "username_lookup_failed",
                str(exc),
            ) from exc

    def verify_password_for_email(self, email: str, password: str) -> None:
        """Ask Supabase Auth to verify the current account password.

        ``email_not_confirmed`` is accepted as a credential proof because GoTrue
        only returns that state after the password/account checks. Any other auth
        rejection remains a password mismatch for this re-verification flow.
        """
        value = (email or "").strip().lower()
        if not value or "@" not in value or not password:
            raise ProviderError("A senha não corresponde.", "password_mismatch")
        try:
            self.sign_in(value, password)
        except ProviderError as exc:
            if exc.code == "email_not_confirmed":
                return
            raise ProviderError("A senha não corresponde.", "password_mismatch", exc.internal or str(exc)) from exc

    def create_friend_request(self, sender_id: str, target_username: str) -> dict[str, Any]:
        """Persist one real friend request in Supabase PostgreSQL.

        The username is resolved server-side from ``public.profiles`` and the
        browser never chooses the receiver UUID. Repeating the same outgoing
        pending request is idempotent; no duplicate row is created.
        """
        sender = (sender_id or "").strip()
        username = (target_username or "").strip().lower()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", sender):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not username or len(username) > 37:
            raise ProviderError("Hum, não funcionou. Confira se o nome de usuário está correto.", "friend_username_not_found")
        if not self.database_configured:
            raise ProviderError("Não foi possível enviar o pedido de amizade agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT p.id::text, p.username
                          FROM public.profiles p
                          JOIN auth.users u ON u.id = p.id
                         WHERE lower(p.username) = lower(%s)
                           AND u.deleted_at IS NULL
                         LIMIT 1
                        """,
                        (username,),
                    )
                    target = cur.fetchone()
                    if not target:
                        raise ProviderError(
                            "Hum, não funcionou. Confira se o nome de usuário está correto.",
                            "friend_username_not_found",
                        )
                    receiver_id = str(target[0])
                    canonical_username = str(target[1] or username).strip().lower()
                    if receiver_id == sender:
                        raise ProviderError(
                            "Hum, não funcionou. Confira se o nome de usuário está correto.",
                            "friend_self_not_allowed",
                        )

                    cur.execute(
                        """
                        SELECT status
                          FROM public.friend_requests
                         WHERE sender_id=%s::uuid AND receiver_id=%s::uuid
                         LIMIT 1
                        """,
                        (receiver_id, sender),
                    )
                    reverse = cur.fetchone()
                    if reverse and str(reverse[0]) in {"pending", "accepted"}:
                        raise ProviderError(
                            "Hum, não funcionou. Confira se o nome de usuário está correto.",
                            "friend_request_conflict",
                        )

                    cur.execute(
                        """
                        INSERT INTO public.friend_requests(sender_id, receiver_id, status)
                        VALUES (%s::uuid, %s::uuid, 'pending')
                        ON CONFLICT (sender_id, receiver_id) DO UPDATE
                            SET status = CASE
                                WHEN public.friend_requests.status IN ('declined','cancelled') THEN 'pending'
                                ELSE public.friend_requests.status
                            END,
                            updated_at = CASE
                                WHEN public.friend_requests.status IN ('declined','cancelled') THEN now()
                                ELSE public.friend_requests.updated_at
                            END
                        RETURNING id::text, status, created_at::text
                        """,
                        (sender, receiver_id),
                    )
                    row = cur.fetchone()
                conn.commit()
            if not row or str(row[1]) != "pending":
                raise ProviderError(
                    "Hum, não funcionou. Confira se o nome de usuário está correto.",
                    "friend_request_conflict",
                )
            return {
                "request_id": str(row[0]),
                "status": "pending",
                "username": canonical_username,
                "receiver_id": receiver_id,
                "created_at": str(row[2]),
            }
        except ProviderError:
            raise
        except Exception as exc:
            detail = str(exc)
            if "friend_requests_no_self" in detail:
                raise ProviderError(
                    "Hum, não funcionou. Confira se o nome de usuário está correto.",
                    "friend_self_not_allowed",
                    detail,
                ) from exc
            raise ProviderError("Não foi possível enviar o pedido de amizade agora.", "friend_request_failed", detail) from exc

    def list_pending_friend_requests(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        """Return caller-scoped sent and received pending requests in one DB round trip.

        The peer identity is resolved on the server from ``public.profiles`` and
        ``auth.users``. The browser never selects another user's UUID.
        """
        actor_id = (user_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", actor_id):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not self.database_configured:
            raise ProviderError("Não foi possível carregar os pedidos pendentes agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT direction,
                               request_id,
                               peer_id,
                               global_name,
                               username,
                               avatar_url,
                               created_at
                          FROM (
                                SELECT 'sent'::text AS direction,
                                       fr.id::text AS request_id,
                                       fr.receiver_id::text AS peer_id,
                                       COALESCE(NULLIF(BTRIM(p.global_name), ''), p.username, 'Usuário') AS global_name,
                                       COALESCE(p.username, '') AS username,
                                       COALESCE(NULLIF(u.raw_user_meta_data->>'avatar_url', ''), '') AS avatar_url,
                                       fr.created_at
                                  FROM public.friend_requests fr
                                  JOIN public.profiles p ON p.id = fr.receiver_id
                                  JOIN auth.users u ON u.id = fr.receiver_id
                                 WHERE fr.sender_id = %s::uuid
                                   AND fr.status = 'pending'
                                   AND u.deleted_at IS NULL
                                UNION ALL
                                SELECT 'received'::text AS direction,
                                       fr.id::text AS request_id,
                                       fr.sender_id::text AS peer_id,
                                       COALESCE(NULLIF(BTRIM(p.global_name), ''), p.username, 'Usuário') AS global_name,
                                       COALESCE(p.username, '') AS username,
                                       COALESCE(NULLIF(u.raw_user_meta_data->>'avatar_url', ''), '') AS avatar_url,
                                       fr.created_at
                                  FROM public.friend_requests fr
                                  JOIN public.profiles p ON p.id = fr.sender_id
                                  JOIN auth.users u ON u.id = fr.sender_id
                                 WHERE fr.receiver_id = %s::uuid
                                   AND fr.status = 'pending'
                                   AND u.deleted_at IS NULL
                               ) pending
                         ORDER BY created_at DESC, request_id DESC
                         LIMIT 400
                        """,
                        (actor_id, actor_id),
                    )
                    rows = cur.fetchall()
            result: dict[str, list[dict[str, Any]]] = {"sent": [], "received": []}
            for row in rows:
                direction = str(row[0] or "")
                if direction not in result:
                    continue
                result[direction].append({
                    "request_id": str(row[1]),
                    "peer_id": str(row[2]),
                    "global_name": str(row[3] or row[4] or "Usuário"),
                    "username": str(row[4] or "").strip().lower(),
                    "avatar_url": str(row[5] or "").strip(),
                    "created_at": str(row[6] or ""),
                })
            return result
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(
                "Não foi possível carregar os pedidos pendentes agora.",
                "friend_requests_list_failed",
                str(exc),
            ) from exc

    def cancel_outgoing_friend_request(self, sender_id: str, request_id: str) -> dict[str, Any]:
        """Delete one outgoing pending request owned by the current actor."""
        sender = (sender_id or "").strip()
        request_value = (request_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", sender):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", request_value):
            raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
        if not self.database_configured:
            raise ProviderError("Não foi possível cancelar o pedido agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM public.friend_requests
                         WHERE id = %s::uuid
                           AND sender_id = %s::uuid
                           AND status = 'pending'
                        RETURNING id::text, receiver_id::text
                        """,
                        (request_value, sender),
                    )
                    row = cur.fetchone()
                conn.commit()
            if not row:
                raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
            return {"request_id": str(row[0]), "receiver_id": str(row[1]), "status": "deleted"}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível cancelar o pedido agora.", "friend_request_cancel_failed", str(exc)) from exc

    def accept_incoming_friend_request(self, receiver_id: str, request_id: str) -> dict[str, Any]:
        """Accept a pending request addressed to the current actor."""
        receiver = (receiver_id or "").strip()
        request_value = (request_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", receiver):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", request_value):
            raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
        if not self.database_configured:
            raise ProviderError("Não foi possível aceitar o pedido agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE public.friend_requests
                           SET status = 'accepted', updated_at = now()
                         WHERE id = %s::uuid
                           AND receiver_id = %s::uuid
                           AND status = 'pending'
                        RETURNING id::text, sender_id::text, status
                        """,
                        (request_value, receiver),
                    )
                    row = cur.fetchone()
                conn.commit()
            if not row:
                raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
            return {"request_id": str(row[0]), "sender_id": str(row[1]), "status": str(row[2])}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível aceitar o pedido agora.", "friend_request_accept_failed", str(exc)) from exc

    def ignore_incoming_friend_request(self, receiver_id: str, request_id: str) -> dict[str, Any]:
        """Delete a pending request addressed to the current actor."""
        receiver = (receiver_id or "").strip()
        request_value = (request_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", receiver):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", request_value):
            raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
        if not self.database_configured:
            raise ProviderError("Não foi possível ignorar o pedido agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM public.friend_requests
                         WHERE id = %s::uuid
                           AND receiver_id = %s::uuid
                           AND status = 'pending'
                        RETURNING id::text, sender_id::text
                        """,
                        (request_value, receiver),
                    )
                    row = cur.fetchone()
                conn.commit()
            if not row:
                raise ProviderError("Pedido de amizade não encontrado.", "friend_request_not_found")
            return {"request_id": str(row[0]), "sender_id": str(row[1]), "status": "deleted"}
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível ignorar o pedido agora.", "friend_request_ignore_failed", str(exc)) from exc

    def create_guild(
        self,
        owner_id: str,
        *,
        name: str,
        template_key: str,
        audience: str,
        icon_media_type: str | None = None,
        icon_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Create one server plus owner membership and its default text channel atomically."""
        owner = (owner_id or "").strip()
        clean_name = (name or "").strip()
        template = (template_key or "custom").strip().lower()
        audience_value = (audience or "friends").strip().lower()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", owner):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not clean_name or len(clean_name) > 100:
            raise ProviderError("O nome do servidor deve ter entre 1 e 100 caracteres.", "guild_name_invalid")
        if template not in {"custom", "gaming", "friends", "study_group", "school_club", "local_community", "artists_creators"}:
            raise ProviderError("Modelo de servidor inválido.", "guild_template_invalid")
        if audience_value not in {"friends", "community", "skipped"}:
            raise ProviderError("Tipo de servidor inválido.", "guild_audience_invalid")
        if icon_bytes is not None:
            if icon_media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp", "image/avif"}:
                raise ProviderError("Formato de imagem não suportado.", "guild_icon_invalid")
            if len(icon_bytes) > 8 * 1024 * 1024:
                raise ProviderError("A imagem do servidor é muito grande.", "guild_icon_too_large")
        icon_hash = hashlib.sha256(icon_bytes).hexdigest() if icon_bytes else None
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO public.guilds(owner_id, name, template_key, audience, icon_media_type, icon_bytes, icon_sha256)
                        VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
                        RETURNING id::text, name, created_at::text
                        """,
                        (owner, clean_name, template, audience_value, icon_media_type, icon_bytes, icon_hash),
                    )
                    guild_row = cur.fetchone()
                    if not guild_row:
                        raise ProviderError("Não foi possível criar o servidor.", "guild_create_failed")
                    guild_id = str(guild_row[0])
                    cur.execute(
                        """
                        INSERT INTO public.guild_members(guild_id, user_id, member_role)
                        VALUES (%s::uuid, %s::uuid, 'owner')
                        ON CONFLICT (guild_id, user_id) DO UPDATE SET member_role='owner'
                        """,
                        (guild_id, owner),
                    )
                    cur.execute(
                        """
                        INSERT INTO public.guild_channels(guild_id, name, channel_type, position)
                        VALUES (%s::uuid, 'general', 'text', 0)
                        RETURNING id::text, name
                        """,
                        (guild_id,),
                    )
                    channel_row = cur.fetchone()
                    if not channel_row:
                        raise ProviderError("Não foi possível criar o canal inicial.", "guild_channel_create_failed")
                    cur.execute(
                        """
                        INSERT INTO public.guild_channels(guild_id, name, channel_type, position)
                        VALUES (%s::uuid, 'general', 'voice', 0)
                        RETURNING id::text, name
                        """,
                        (guild_id,),
                    )
                    voice_channel_row = cur.fetchone()
                    if not voice_channel_row:
                        raise ProviderError("Não foi possível criar o canal de voz inicial.", "guild_voice_channel_create_failed")
                conn.commit()
            return {
                "guild_id": guild_id,
                "name": str(guild_row[1]),
                "channel_id": str(channel_row[0]),
                "channel_name": str(channel_row[1]),
                "voice_channel_id": str(voice_channel_row[0]),
                "voice_channel_name": str(voice_channel_row[1]),
                "template_key": template,
                "audience": audience_value,
                "has_icon": bool(icon_bytes),
                "icon_sha256": icon_hash or "",
                "created_at": str(guild_row[2]),
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível criar o servidor agora.", "guild_create_failed", str(exc)) from exc

    def list_user_guilds(self, user_id: str) -> list[dict[str, Any]]:
        """Return only servers where the current actor is a member, with first text channel."""
        uid = (user_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uid):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT g.id::text,
                               g.name,
                               (g.icon_bytes IS NOT NULL) AS has_icon,
                               COALESCE(g.icon_sha256, ''),
                               ch.id::text,
                               ch.name,
                               gm.member_role,
                               g.created_at::text
                          FROM public.guild_members gm
                          JOIN public.guilds g ON g.id = gm.guild_id
                          JOIN auth.users owner_user ON owner_user.id = g.owner_id AND owner_user.deleted_at IS NULL
                          LEFT JOIN LATERAL (
                              SELECT id, name
                                FROM public.guild_channels
                               WHERE guild_id = g.id AND channel_type='text'
                               ORDER BY position ASC, created_at ASC, id ASC
                               LIMIT 1
                          ) ch ON true
                         WHERE gm.user_id = %s::uuid
                         ORDER BY gm.joined_at ASC, g.created_at ASC, g.id ASC
                         LIMIT 200
                        """,
                        (uid,),
                    )
                    rows = cur.fetchall()
            return [{
                "id": str(r[0]),
                "name": str(r[1] or "Servidor"),
                "has_icon": bool(r[2]),
                "icon_sha256": str(r[3] or ""),
                "default_channel_id": str(r[4] or ""),
                "default_channel_name": str(r[5] or "general"),
                "member_role": str(r[6] or "member"),
                "created_at": str(r[7] or ""),
            } for r in rows]
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível carregar os servidores agora.", "guild_list_failed", str(exc)) from exc

    def get_guild_view_for_user(self, user_id: str, guild_id: str, channel_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Resolve one guild route and its channels in a single DB connection.

        The actor's live ``auth.users`` row is joined into the authorization
        query, so SPA navigation does not need a separate identity round trip.
        This keeps the read path fail-closed while eliminating redundant
        connection setup and the full guild-list reload on every switch.
        """
        uid = (user_id or "").strip()
        gid = (guild_id or "").strip()
        cid = (channel_id or "").strip()
        if not all(re.fullmatch(r"[0-9a-fA-F-]{36}", value) for value in (uid, gid, cid)):
            raise ProviderError("Servidor ou canal não encontrado.", "guild_not_found")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT g.id::text,
                               g.name,
                               g.owner_id::text,
                               (g.icon_bytes IS NOT NULL) AS has_icon,
                               COALESCE(g.icon_sha256, ''),
                               ch.id::text,
                               ch.name,
                               ch.channel_type,
                               gm.member_role
                          FROM public.guild_members gm
                          JOIN auth.users actor_user
                            ON actor_user.id = gm.user_id
                           AND actor_user.deleted_at IS NULL
                          JOIN public.guilds g ON g.id = gm.guild_id
                          JOIN public.guild_channels ch ON ch.guild_id = g.id
                          JOIN auth.users owner_user
                            ON owner_user.id = g.owner_id
                           AND owner_user.deleted_at IS NULL
                         WHERE gm.user_id = %s::uuid
                           AND g.id = %s::uuid
                           AND ch.id = %s::uuid
                         LIMIT 1
                        """,
                        (uid, gid, cid),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ProviderError("Servidor ou canal não encontrado.", "guild_not_found")
                    current = {
                        "id": str(row[0]), "name": str(row[1]), "owner_id": str(row[2]),
                        "has_icon": bool(row[3]), "icon_sha256": str(row[4] or ""),
                        "channel_id": str(row[5]), "channel_name": str(row[6]),
                        "channel_type": str(row[7]), "member_role": str(row[8] or "member"),
                    }
                    cur.execute(
                        """
                        SELECT ch.id::text, ch.name, ch.channel_type, ch.position
                          FROM public.guild_members gm
                          JOIN auth.users actor_user
                            ON actor_user.id = gm.user_id
                           AND actor_user.deleted_at IS NULL
                          JOIN public.guild_channels ch ON ch.guild_id = gm.guild_id
                         WHERE gm.user_id = %s::uuid
                           AND gm.guild_id = %s::uuid
                         ORDER BY CASE ch.channel_type WHEN 'text' THEN 0 ELSE 1 END,
                                  ch.position ASC, ch.created_at ASC, ch.id ASC
                        """,
                        (uid, gid),
                    )
                    rows = cur.fetchall()
            if not rows:
                raise ProviderError("Servidor não encontrado.", "guild_not_found")
            channels = [{
                "id": str(item[0]),
                "name": str(item[1] or "general"),
                "channel_type": str(item[2] or "text"),
                "position": int(item[3] or 0),
            } for item in rows]
            return current, channels
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível carregar o servidor agora.", "guild_load_failed", str(exc)) from exc

    def get_guild_channel_for_user(self, user_id: str, guild_id: str, channel_id: str) -> dict[str, Any]:
        """Resolve one guild/channel only when the actor is a member."""
        uid = (user_id or "").strip()
        gid = (guild_id or "").strip()
        cid = (channel_id or "").strip()
        if not all(re.fullmatch(r"[0-9a-fA-F-]{36}", value) for value in (uid, gid, cid)):
            raise ProviderError("Servidor ou canal não encontrado.", "guild_not_found")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT g.id::text,
                               g.name,
                               g.owner_id::text,
                               (g.icon_bytes IS NOT NULL) AS has_icon,
                               COALESCE(g.icon_sha256, ''),
                               ch.id::text,
                               ch.name,
                               ch.channel_type,
                               gm.member_role
                          FROM public.guild_members gm
                          JOIN public.guilds g ON g.id = gm.guild_id
                          JOIN public.guild_channels ch ON ch.guild_id = g.id
                          JOIN auth.users owner_user ON owner_user.id = g.owner_id AND owner_user.deleted_at IS NULL
                         WHERE gm.user_id = %s::uuid
                           AND g.id = %s::uuid
                           AND ch.id = %s::uuid
                         LIMIT 1
                        """,
                        (uid, gid, cid),
                    )
                    row = cur.fetchone()
            if not row:
                raise ProviderError("Servidor ou canal não encontrado.", "guild_not_found")
            return {
                "id": str(row[0]), "name": str(row[1]), "owner_id": str(row[2]),
                "has_icon": bool(row[3]), "icon_sha256": str(row[4] or ""),
                "channel_id": str(row[5]), "channel_name": str(row[6]),
                "channel_type": str(row[7]), "member_role": str(row[8] or "member"),
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível carregar o servidor agora.", "guild_load_failed", str(exc)) from exc

    def list_guild_channels_for_user(self, user_id: str, guild_id: str) -> list[dict[str, Any]]:
        """Return text/voice channels only when the actor belongs to the guild."""
        uid = (user_id or "").strip()
        gid = (guild_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uid) or not re.fullmatch(r"[0-9a-fA-F-]{36}", gid):
            raise ProviderError("Servidor não encontrado.", "guild_not_found")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT ch.id::text, ch.name, ch.channel_type, ch.position
                          FROM public.guild_members gm
                          JOIN public.guild_channels ch ON ch.guild_id = gm.guild_id
                         WHERE gm.user_id = %s::uuid
                           AND gm.guild_id = %s::uuid
                         ORDER BY CASE ch.channel_type WHEN 'text' THEN 0 ELSE 1 END,
                                  ch.position ASC, ch.created_at ASC, ch.id ASC
                        """,
                        (uid, gid),
                    )
                    rows = cur.fetchall()
            if not rows:
                raise ProviderError("Servidor não encontrado.", "guild_not_found")
            return [{
                "id": str(row[0]),
                "name": str(row[1] or "general"),
                "channel_type": str(row[2] or "text"),
                "position": int(row[3] or 0),
            } for row in rows]
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível carregar os canais agora.", "guild_channels_load_failed", str(exc)) from exc

    @staticmethod
    def _voice_uuid(value: str, *, code: str = "voice_invalid") -> str:
        clean = (value or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", clean):
            raise ProviderError("Sessão de voz inválida.", code)
        return clean

    @staticmethod
    def _voice_participants(cur: Any, channel_id: str) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT vs.id::text,
                   vs.user_id::text,
                   COALESCE(NULLIF(btrim(p.username), ''), split_part(u.email, '@', 1), 'usuário') AS username,
                   COALESCE(NULLIF(btrim(p.global_name), ''), NULLIF(btrim(p.username), ''), split_part(u.email, '@', 1), 'usuário') AS global_name,
                   vs.joined_at::text
              FROM public.voice_sessions vs
              JOIN auth.users u ON u.id = vs.user_id AND u.deleted_at IS NULL
              LEFT JOIN public.profiles p ON p.id = vs.user_id
             WHERE vs.channel_id = %s::uuid
               AND vs.last_seen_at >= now() - interval '20 seconds'
             ORDER BY vs.joined_at ASC, vs.id ASC
            """,
            (channel_id,),
        )
        return [{
            "sessionId": str(row[0]),
            "userId": str(row[1]),
            "username": str(row[2] or "usuário"),
            "globalName": str(row[3] or row[2] or "usuário"),
            "joinedAt": str(row[4] or ""),
        } for row in cur.fetchall()]

    @staticmethod
    def _voice_cleanup(cur: Any) -> None:
        cur.execute("DELETE FROM public.voice_sessions WHERE last_seen_at < now() - interval '20 seconds'")
        cur.execute("DELETE FROM public.voice_signals WHERE created_at < now() - interval '90 seconds'")

    def voice_join(self, user_id: str, guild_id: str, channel_id: str) -> dict[str, Any]:
        uid = self._voice_uuid(user_id, code="invalid_actor")
        gid = self._voice_uuid(guild_id, code="guild_not_found")
        cid = self._voice_uuid(channel_id, code="voice_channel_not_found")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    self._voice_cleanup(cur)
                    cur.execute(
                        """
                        SELECT ch.id::text, ch.name, g.name
                          FROM public.guild_members gm
                          JOIN public.guilds g ON g.id = gm.guild_id
                          JOIN public.guild_channels ch ON ch.guild_id = g.id
                         WHERE gm.user_id = %s::uuid
                           AND g.id = %s::uuid
                           AND ch.id = %s::uuid
                           AND ch.channel_type = 'voice'
                         LIMIT 1
                        """,
                        (uid, gid, cid),
                    )
                    channel = cur.fetchone()
                    if not channel:
                        raise ProviderError("Canal de voz não encontrado.", "voice_channel_not_found")
                    cur.execute("DELETE FROM public.voice_sessions WHERE channel_id=%s::uuid AND user_id=%s::uuid", (cid, uid))
                    cur.execute(
                        """
                        INSERT INTO public.voice_sessions(guild_id, channel_id, user_id)
                        VALUES (%s::uuid, %s::uuid, %s::uuid)
                        RETURNING id::text, joined_at::text
                        """,
                        (gid, cid, uid),
                    )
                    session = cur.fetchone()
                    participants = self._voice_participants(cur, cid)
                conn.commit()
            if not session:
                raise ProviderError("Não foi possível abrir a sessão de voz.", "voice_join_failed")
            return {
                "sessionId": str(session[0]),
                "joinedAt": str(session[1]),
                "channelId": str(channel[0]),
                "channelName": str(channel[1] or "general"),
                "guildName": str(channel[2] or "Servidor"),
                "participants": participants,
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível conectar ao canal de voz agora.", "voice_join_failed", str(exc)) from exc

    def voice_state(self, user_id: str, voice_session_id: str) -> dict[str, Any]:
        uid = self._voice_uuid(user_id, code="invalid_actor")
        sid = self._voice_uuid(voice_session_id, code="voice_session_invalid")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    self._voice_cleanup(cur)
                    cur.execute(
                        """
                        UPDATE public.voice_sessions
                           SET last_seen_at = now()
                         WHERE id = %s::uuid
                           AND user_id = %s::uuid
                        RETURNING channel_id::text, guild_id::text
                        """,
                        (sid, uid),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ProviderError("A sessão de voz expirou.", "voice_session_expired")
                    cid, gid = str(row[0]), str(row[1])
                    participants = self._voice_participants(cur, cid)
                    cur.execute(
                        """
                        SELECT id, sender_session_id::text, signal_type, payload, created_at::text
                          FROM public.voice_signals
                         WHERE target_session_id = %s::uuid
                         ORDER BY id ASC
                         LIMIT 200
                        """,
                        (sid,),
                    )
                    signal_rows = cur.fetchall()
                    signal_ids = [int(item[0]) for item in signal_rows]
                    if signal_ids:
                        cur.execute("DELETE FROM public.voice_signals WHERE id = ANY(%s)", (signal_ids,))
                conn.commit()
            return {
                "sessionId": sid,
                "guildId": gid,
                "channelId": cid,
                "participants": participants,
                "signals": [{
                    "id": int(item[0]),
                    "senderSessionId": str(item[1]),
                    "type": str(item[2]),
                    "payload": item[3] if isinstance(item[3], dict) else {},
                    "createdAt": str(item[4] or ""),
                } for item in signal_rows],
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível atualizar a sessão de voz.", "voice_state_failed", str(exc)) from exc

    def voice_signal(
        self,
        user_id: str,
        voice_session_id: str,
        target_session_id: str,
        signal_type: str,
        payload: dict[str, Any],
    ) -> None:
        uid = self._voice_uuid(user_id, code="invalid_actor")
        sid = self._voice_uuid(voice_session_id, code="voice_session_invalid")
        target = self._voice_uuid(target_session_id, code="voice_target_invalid")
        if sid == target:
            raise ProviderError("Destino de voz inválido.", "voice_target_invalid")
        kind = (signal_type or "").strip().lower()
        if kind not in {"offer", "answer", "ice"}:
            raise ProviderError("Tipo de sinal de voz inválido.", "voice_signal_invalid")
        if not isinstance(payload, dict):
            raise ProviderError("Payload de sinal inválido.", "voice_signal_invalid")
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 65536:
            raise ProviderError("Payload de sinal excede o limite.", "voice_signal_too_large")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    self._voice_cleanup(cur)
                    cur.execute(
                        """
                        SELECT sender.channel_id::text
                          FROM public.voice_sessions sender
                          JOIN public.voice_sessions tgt ON tgt.id = %s::uuid
                         WHERE sender.id = %s::uuid
                           AND sender.user_id = %s::uuid
                           AND sender.channel_id = tgt.channel_id
                           AND sender.last_seen_at >= now() - interval '20 seconds'
                           AND tgt.last_seen_at >= now() - interval '20 seconds'
                         LIMIT 1
                        """,
                        (target, sid, uid),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise ProviderError("Destino de voz não está disponível.", "voice_target_unavailable")
                    cur.execute(
                        """
                        INSERT INTO public.voice_signals(channel_id, sender_session_id, target_session_id, signal_type, payload)
                        VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s::jsonb)
                        """,
                        (str(row[0]), sid, target, kind, encoded),
                    )
                conn.commit()
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível enviar o sinal de voz.", "voice_signal_failed", str(exc)) from exc

    def voice_leave(self, user_id: str, voice_session_id: str) -> bool:
        uid = self._voice_uuid(user_id, code="invalid_actor")
        sid = self._voice_uuid(voice_session_id, code="voice_session_invalid")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM public.voice_sessions WHERE id=%s::uuid AND user_id=%s::uuid RETURNING id",
                        (sid, uid),
                    )
                    deleted = cur.fetchone() is not None
                conn.commit()
            return deleted
        except Exception as exc:
            raise ProviderError("Não foi possível encerrar a sessão de voz.", "voice_leave_failed", str(exc)) from exc

    def get_guild_icon_for_user(self, user_id: str, guild_id: str) -> tuple[bytes, str, str]:
        """Return a server icon only to a current guild member."""
        uid = (user_id or "").strip()
        gid = (guild_id or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uid) or not re.fullmatch(r"[0-9a-fA-F-]{36}", gid):
            raise ProviderError("Ícone não encontrado.", "guild_icon_not_found")
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT g.icon_bytes, g.icon_media_type, COALESCE(g.icon_sha256, '')
                          FROM public.guild_members gm
                          JOIN public.guilds g ON g.id = gm.guild_id
                         WHERE gm.user_id = %s::uuid
                           AND g.id = %s::uuid
                           AND g.icon_bytes IS NOT NULL
                         LIMIT 1
                        """,
                        (uid, gid),
                    )
                    row = cur.fetchone()
            if not row:
                raise ProviderError("Ícone não encontrado.", "guild_icon_not_found")
            return bytes(row[0]), str(row[1] or "application/octet-stream"), str(row[2] or "")
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível carregar o ícone agora.", "guild_icon_load_failed", str(exc)) from exc

    def change_account_email(self, user_id: str, current_email: str, new_email: str, password: str) -> dict[str, Any]:
        """Change the session owner's email after a fresh password proof.

        The administrative Auth operation remains server-side. The account is
        intentionally left unconfirmed and a normal signup confirmation is
        requested for the new address so the local actor can remain ``pending``.
        """
        uid = (user_id or "").strip()
        current = (current_email or "").strip().lower()
        value = (new_email or "").strip().lower()
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", uid):
            raise ProviderError("Sessão inválida.", "invalid_actor")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) or len(value) > 320:
            raise ProviderError("Digite um endereço de e-mail válido.", "email_invalid")
        self.verify_password_for_email(current, password)
        if self.auth_email_exists(value):
            raise ProviderError("O e-mail já está registrado.", "email_exists")
        try:
            updated = self.update_user(uid, {"email": value, "email_confirm": False})
            result = self._extract_admin_user(updated)
        except ProviderError:
            raise
        except Exception as exc:
            detail = str(exc)
            code = self._error_code(exc)
            lower = detail.lower()
            if code in {"email_exists", "user_already_exists"} or "already registered" in lower:
                raise ProviderError("O e-mail já está registrado.", "email_exists", detail) from exc
            raise ProviderError("Não foi possível alterar o e-mail agora.", code, detail) from exc

        sent = False
        send_code = ""
        try:
            self.resend_signup_confirmation(value)
            sent = True
        except ProviderError as exc:
            send_code = exc.code
        result.update({
            "email": value,
            "email_confirmed": False,
            "verification_kind": "signup",
            "confirmation_email_sent": sent,
        })
        if send_code:
            result["confirmation_email_code"] = send_code
        return result

    def sign_up(self, email: str, password: str, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        client = self._public_client()
        payload: dict[str, Any] = {"email": email, "password": password}
        if metadata:
            payload["options"] = {"data": metadata}
        try:
            response = client.auth.sign_up(payload)
            result = self._extract_auth_response(response)
            result["creation_mode"] = "public-signup"
            result["verification_kind"] = "signup"
            return result
        except Exception as exc:
            detail = str(exc)
            if "profiles_username_unique" in detail or "username_unique" in detail:
                raise ProviderError("Nome de usuário indisponível.", "username_unavailable", detail) from exc
            raise ProviderError("Não foi possível concluir o cadastro.", self._error_code(exc), detail) from exc

    def auth_user_exists_by_id(self, user_id: str) -> bool:
        """Return whether a Supabase Auth principal is still active.

        Hard-deleted rows are absent and soft-deleted rows have ``deleted_at``
        populated. Browser sessions are valid only while this predicate remains
        true; the local SQLite session is never an independent source of account
        existence.
        """
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id or ""):
            return False
        if not self.database_configured:
            raise ProviderError("Não foi possível validar a sessão agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT EXISTS (SELECT 1 FROM auth.users WHERE id=%s::uuid AND deleted_at IS NULL)",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    return bool(row and row[0])
        except Exception as exc:
            raise ProviderError("Não foi possível validar a sessão agora.", "session_identity_lookup_failed", str(exc)) from exc

    def auth_user_status(self, user_id: str) -> dict[str, Any]:
        """Resolve verification/profile state from trusted server-side data."""
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id or ""):
            raise ProviderError("Identificador de usuário inválido.", "invalid_user_id")
        if not self.database_configured:
            raise ProviderError("Não foi possível consultar a conta agora.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                            u.email,
                            (u.email_confirmed_at IS NOT NULL) AS email_confirmed,
                            COALESCE(p.username, nullif(btrim(u.raw_user_meta_data->>'username'), '')) AS username,
                            COALESCE(p.global_name, nullif(btrim(u.raw_user_meta_data->>'global_name'), '')) AS global_name
                        FROM auth.users u
                        LEFT JOIN public.profiles p ON p.id = u.id
                        WHERE u.id = %s::uuid
                        LIMIT 1
                        """,
                        (user_id,),
                    )
                    row = cur.fetchone()
            if not row:
                raise ProviderError("Conta não encontrada.", "user_not_found")
            return {
                "user_id": user_id,
                "email": str(row[0] or ""),
                "email_confirmed": bool(row[1]),
                "username": str(row[2] or "").strip().lower(),
                "global_name": str(row[3] or "").strip(),
            }
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("Não foi possível consultar a conta agora.", "user_status_failed", str(exc)) from exc

    def resend_signup_confirmation(self, email: str) -> None:
        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise ProviderError("E-mail inválido.", "invalid_email")
        try:
            self._auth_api_json("resend", {"type": "signup", "email": email}, timeout=10)
        except ProviderError as exc:
            # Keep provider internals out of the UI while preserving a stable code.
            raise ProviderError("Não foi possível reenviar o e-mail de verificação agora.", exc.code, exc.internal) from exc

    def test_public_connection(self, timeout: int = 8) -> tuple[bool, str]:
        if not self.public_configured:
            return False, "URL ou chave publicável ausente."
        # New sb_publishable_* keys are opaque API keys, not JWTs.  Send the
        # key only in the apikey header.  Supplying it as Authorization: Bearer
        # can be rejected by current Supabase gateways because that header is
        # reserved for a user/session JWT.
        request = urllib.request.Request(
            f"{self.url}/auth/v1/settings",
            headers={
                "apikey": self.publishable_key,
                "Accept": "application/json",
                "User-Agent": "local-admin-connection-test/1.0",
            },
            method="GET",
        )
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                status = int(getattr(response, "status", 0) or 0)
                return status == 200, f"HTTP {status}"
        except urllib.error.HTTPError as exc:
            return False, f"HTTP {exc.code}"
        except Exception as exc:
            return False, exc.__class__.__name__

    def test_admin_connection(self) -> tuple[bool, str]:
        if not self.admin_configured:
            return False, "Chave administrativa ausente."
        try:
            self.list_users(page=1, per_page=1)
            return True, f"Auth Admin OK ({self.admin_key_kind})"
        except Exception as exc:
            return False, f"{self._error_code(exc)}"

    def test_jwks(self, timeout: int = 8) -> tuple[bool, str]:
        if not self.jwks_url:
            return False, "Discovery URL ausente."
        req = urllib.request.Request(
            self.jwks_url,
            headers={"Accept": "application/json", "User-Agent": "local-admin-jwks-test/1.0"},
            method="GET",
        )
        context = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
                raw = response.read().decode("utf-8")
                body = json.loads(raw)
            keys = body.get("keys") if isinstance(body, dict) else None
            if not isinstance(keys, list):
                return False, "JWKS sem array keys."
            if self.jwks_kid:
                key = next((item for item in keys if isinstance(item, dict) and item.get("kid") == self.jwks_kid), None)
                if not key:
                    return False, "KID esperado não encontrado."
                if key.get("alg") != "ES256" or key.get("kty") != "EC" or key.get("crv") != "P-256":
                    return False, "KID encontrado com parâmetros inesperados."
                return True, "JWKS ES256/P-256 OK"
            return True, f"JWKS OK ({len(keys)} chave(s))"
        except Exception as exc:
            return False, exc.__class__.__name__

    @staticmethod
    def _b64url_decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))

    def verify_legacy_api_keys(self) -> tuple[bool, str]:
        """Validate the supplied legacy anon/service_role JWTs against the
        legacy JWT secret without minting any token or exposing the secret.
        """
        if not (self.legacy_jwt_secret and self.legacy_anon_key and self.service_role_key):
            return False, "Conjunto legado incompleto."

        def verify(token: str, expected_role: str) -> bool:
            try:
                header_b64, payload_b64, sig_b64 = token.split(".")
                signed = f"{header_b64}.{payload_b64}".encode("ascii")
                expected = hmac.new(self.legacy_jwt_secret.encode("utf-8"), signed, hashlib.sha256).digest()
                actual = self._b64url_decode(sig_b64)
                if not hmac.compare_digest(expected, actual):
                    return False
                header = json.loads(self._b64url_decode(header_b64))
                payload = json.loads(self._b64url_decode(payload_b64))
                return (
                    header.get("alg") == "HS256"
                    and payload.get("ref") == self.project_ref
                    and payload.get("role") == expected_role
                    and int(payload.get("exp") or 0) > int(time.time())
                )
            except Exception:
                return False

        anon_ok = verify(self.legacy_anon_key, "anon")
        service_ok = verify(self.service_role_key, "service_role")
        return anon_ok and service_ok, "anon/service_role coerentes" if anon_ok and service_ok else "falha na validação local"

    def database_health(self) -> dict[str, str]:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: conexão não configurada.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), current_user, current_setting('server_version')")
                row = cur.fetchone()
                return {"database": str(row[0]), "user": str(row[1]), "version": str(row[2])}

    @staticmethod
    def _validate_ident(value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]{0,62}", value or ""):
            raise ProviderError("Identificador SQL inválido.", "invalid_identifier")
        return value

    def enable_rls(self, schema: str, table: str, *, force: bool = False) -> None:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: conexão não configurada.", "db_password_missing")
        schema = self._validate_ident(schema)
        table = self._validate_ident(table)
        if schema not in self.RLS_MANAGED_SCHEMAS:
            raise ProviderError("RLS pelo painel só pode ser alterado no schema public do aplicativo.", "rls_managed_schema_denied")
        try:
            import psycopg
            from psycopg import sql
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        command = sql.SQL("ALTER TABLE {}.{} {} ROW LEVEL SECURITY").format(
            sql.Identifier(schema), sql.Identifier(table), sql.SQL("FORCE" if force else "ENABLE")
        )
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(command)
            conn.commit()

    @staticmethod
    def _single_statement(sql_text: str) -> tuple[str, str]:
        statement = (sql_text or "").strip()
        if not statement or len(statement) > 20000:
            raise ProviderError("Comando SQL vazio ou excessivamente longo.", "sql_invalid")
        trimmed = statement.rstrip().rstrip(";").rstrip()
        if ";" in trimmed:
            raise ProviderError("Somente um comando SQL por execução é permitido.", "sql_multiple_statements")
        without_comments = re.sub(r"^\s*(?:--[^\n]*\n|/\*.*?\*/\s*)*", "", trimmed, flags=re.S)
        match = re.match(r"([A-Za-z]+)", without_comments)
        if not match:
            raise ProviderError("Comando SQL não reconhecido.", "sql_invalid")
        return trimmed, match.group(1).upper()

    def execute_sql(self, sql_text: str, *, allow_write: bool = False) -> dict[str, Any]:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: conexão não configurada.", "db_password_missing")
        statement, keyword = self._single_statement(sql_text)
        blocked = re.compile(
            r"\b(?:ALTER\s+SYSTEM|CREATE\s+(?:ROLE|USER)|ALTER\s+(?:ROLE|USER)|DROP\s+(?:ROLE|USER)|"
            r"COPY\b.*\bPROGRAM\b|REASSIGN\s+OWNED|SECURITY\s+LABEL)\b",
            re.I | re.S,
        )
        if blocked.search(statement):
            raise ProviderError("Comando bloqueado pela política do plano de controle.", "sql_blocked")
        # Supabase-managed schemas are readable for diagnosis but write operations
        # must go through their supported APIs. Direct DDL/DML there can break Auth
        # or platform services. Application writes are limited to public/app_private.
        if allow_write and re.search(r"\b(?:auth|storage|realtime|extensions|graphql|vault)\s*\.", statement, re.I):
            raise ProviderError("Alteração direta em schema gerenciado pelo Supabase foi bloqueada.", "sql_managed_schema_blocked")
        read_keywords = {"SELECT", "SHOW", "EXPLAIN", "VALUES", "WITH"}
        write_keywords = {"CREATE", "ALTER", "DROP", "COMMENT", "GRANT", "REVOKE", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "DO", "WITH"}
        if allow_write:
            if keyword not in write_keywords:
                raise ProviderError("Tipo de comando não autorizado no modo de alteração.", "sql_not_allowlisted")
        elif keyword not in read_keywords:
            raise ProviderError("Comando exige modo de alteração e confirmação explícita.", "sql_write_denied")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        started = time.monotonic()
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '10s'")
                if not allow_write:
                    cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(statement)
                columns = [desc.name for desc in cur.description] if cur.description else []
                rows: list[list[Any]] = []
                truncated = False
                if cur.description:
                    fetched = cur.fetchmany(201)
                    truncated = len(fetched) > 200
                    for row in fetched[:200]:
                        rows.append([None if value is None else str(value)[:4000] for value in row])
                rowcount = int(cur.rowcount or 0)
            if allow_write:
                conn.commit()
            else:
                conn.rollback()
        return {
            "keyword": keyword,
            "columns": columns[:50],
            "rows": [row[:50] for row in rows],
            "rowcount": rowcount,
            "truncated": truncated or len(columns) > 50,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    def list_users(self, page: int = 1, per_page: int = 100):
        client = self._admin_client()
        return client.auth.admin.list_users(page=page, per_page=per_page)

    def create_user(
        self,
        email: str,
        password: str,
        email_confirm: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ):
        client = self._admin_client()
        attributes: dict[str, Any] = {
            "email": email,
            "password": password,
            "email_confirm": bool(email_confirm),
        }
        if metadata:
            attributes["user_metadata"] = metadata
        return client.auth.admin.create_user(attributes)

    def create_registration_user(
        self,
        email: str,
        password: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create the application account through the trusted Auth Admin path.

        The browser remains anonymous and never receives an administrative key.
        The Flask registration endpoint performs validation/rate limiting before
        invoking this method.  The account is intentionally created unconfirmed;
        a normal ``signup`` confirmation email is then requested through Auth's
        public resend endpoint.  Email delivery is best-effort: failure to send
        does not roll back an otherwise valid account, so the authenticated shell
        can expose the existing **Reenviar e-mail** action for retry.
        """
        if not self.admin_configured:
            raise ProviderError(
                "Cadastro indisponível: autoridade server-side não configurada.",
                "admin_key_missing",
            )
        created_id = ""
        try:
            created = self.create_user(email, password, email_confirm=False, metadata=metadata)
            result = self._extract_admin_user(created)
            created_id = result.get("user_id") or ""
            if not created_id:
                raise ProviderError("O provedor não retornou o usuário criado.", "missing_user_id")

            # create_user() does not send confirmation mail. Supabase Auth's
            # /resend type=signup accepts an existing unconfirmed user and calls
            # the normal sendConfirmation flow. Keep this best-effort so SMTP or
            # provider delivery problems never turn a successfully persisted
            # account into an orphaned client-side failure.
            confirmation_email_sent = False
            confirmation_email_code = ""
            try:
                self.resend_signup_confirmation(email)
                confirmation_email_sent = True
            except ProviderError as mail_exc:
                confirmation_email_code = mail_exc.code

            result["creation_mode"] = "server-admin-create"
            result["verification_kind"] = "signup"
            result["email_confirmed"] = False
            result["has_session"] = False
            result["confirmation_email_sent"] = confirmation_email_sent
            if confirmation_email_code:
                result["confirmation_email_code"] = confirmation_email_code
            return result
        except ProviderError:
            raise
        except Exception as exc:
            detail = str(exc)
            if "profiles_username_unique" in detail or "username_unique" in detail:
                raise ProviderError("Nome de usuário indisponível.", "username_unavailable", detail) from exc
            code = self._error_code(exc)
            lower_detail = detail.lower()
            if code in {"user_already_exists", "email_exists"} or "already been registered" in lower_detail or "already registered" in lower_detail:
                raise ProviderError("Já existe uma conta com este e-mail.", "email_exists", detail) from exc
            raise ProviderError("Não foi possível concluir o cadastro.", code, detail) from exc

    def invite_user(self, email: str, metadata: Optional[dict[str, Any]] = None):
        client = self._admin_client()
        options: dict[str, Any] = {}
        if metadata:
            options["data"] = metadata
        if options:
            return client.auth.admin.invite_user_by_email(email, options)
        return client.auth.admin.invite_user_by_email(email)

    @staticmethod
    def _extract_admin_user(response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            user = response.get("user") or response
        else:
            user = getattr(response, "user", None) or response

        def value(name: str, default: Any = "") -> Any:
            if isinstance(user, dict):
                return user.get(name, default)
            return getattr(user, name, default)

        metadata = value("user_metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "user_id": str(value("id") or ""),
            "email": str(value("email") or ""),
            "username": str(metadata.get("username") or "").strip().lower(),
            "global_name": str(metadata.get("global_name") or "").strip(),
            "email_confirmed": bool(value("email_confirmed_at", None) or value("confirmed_at", None)),
            "access_token": None,
            "refresh_token": None,
            "expires_at": None,
            "has_session": False,
        }

    def invite_registration_user(self, email: str, password: str, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Create an unconfirmed account through the trusted invite path.

        This is used only when Supabase explicitly reports that public sign-up
        is disabled. The administrative key never leaves the server. The invite
        creates/sends the verification email; the chosen password and metadata
        are then attached server-side. A partial create is rolled back best-effort.
        """
        if not self.admin_configured:
            raise ProviderError("Cadastro indisponível: criação pública está desativada e o fallback seguro não está configurado.", "admin_key_missing")
        created_id = ""
        try:
            invited = self.invite_user(email, metadata)
            result = self._extract_admin_user(invited)
            created_id = result.get("user_id") or ""
            if not created_id:
                raise ProviderError("O provedor não retornou o usuário convidado.", "missing_user_id")
            attributes: dict[str, Any] = {"password": password}
            if metadata:
                attributes["user_metadata"] = metadata
            updated = self.update_user(created_id, attributes)
            updated_result = self._extract_admin_user(updated)
            if updated_result.get("user_id"):
                result.update(updated_result)
            result["creation_mode"] = "server-invite"
            result["verification_kind"] = "invite"
            result["email_confirmed"] = False
            result["has_session"] = False
            return result
        except ProviderError:
            if created_id:
                try:
                    self.delete_user(created_id, soft=False)
                except Exception:
                    pass
            raise
        except Exception as exc:
            if created_id:
                try:
                    self.delete_user(created_id, soft=False)
                except Exception:
                    pass
            detail = str(exc)
            if "profiles_username_unique" in detail or "username_unique" in detail:
                raise ProviderError("Nome de usuário indisponível.", "username_unavailable", detail) from exc
            raise ProviderError("Não foi possível concluir o cadastro.", self._error_code(exc), detail) from exc

    def update_user(self, user_id: str, attributes: dict[str, Any]):
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id or ""):
            raise ProviderError("Identificador de usuário inválido.", "invalid_user_id")
        if not attributes:
            raise ProviderError("Nenhuma alteração informada.", "no_changes")
        client = self._admin_client()
        return client.auth.admin.update_user_by_id(user_id, attributes)

    def delete_user(self, user_id: str, *, soft: bool = False):
        if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id or ""):
            raise ProviderError("Identificador de usuário inválido.", "invalid_user_id")
        client = self._admin_client()
        return client.auth.admin.delete_user(user_id, should_soft_delete=bool(soft))

    def db_dsn(self) -> str:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: senha da conexão direta não configurada.", "db_password_missing")
        password = urllib.parse.quote(self.db_password, safe="")
        host = self.db_host
        return f"postgresql://postgres:{password}@{host}:5432/postgres?sslmode=require"

    MANAGED_APPLICATION_SCHEMAS = frozenset({"public", "app_private"})
    RLS_MANAGED_SCHEMAS = frozenset({"public"})

    def list_schemas(self) -> list[str]:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: senha da conexão direta não configurada.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        sql = """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname NOT IN ('pg_catalog', 'information_schema')
              AND nspname NOT LIKE 'pg_toast%'
              AND nspname NOT LIKE 'pg_temp_%'
            ORDER BY CASE WHEN nspname='public' THEN 0 WHEN nspname='app_private' THEN 1 ELSE 2 END, nspname
        """
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [str(row[0]) for row in cur.fetchall()]

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: senha da conexão direta não configurada.", "db_password_missing")
        if schema is not None:
            schema = self._validate_ident(schema)
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        sql = """
            SELECT n.nspname AS schemaname, c.relname AS tablename,
                   pg_get_userbyid(c.relowner) AS owner,
                   c.relrowsecurity AS rls_enabled,
                   c.relforcerowsecurity AS rls_forced,
                   c.reltuples::bigint AS estimated_rows,
                   pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
                   (SELECT count(*) FROM pg_catalog.pg_attribute a
                    WHERE a.attrelid=c.oid AND a.attnum > 0 AND NOT a.attisdropped) AS columns
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r','p')
              AND n.nspname NOT IN ('pg_catalog', 'information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
              AND (%s IS NULL OR n.nspname=%s)
            ORDER BY n.nspname, c.relname
        """
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (schema, schema))
                return [{
                    "schema": row[0], "table": row[1], "owner": row[2],
                    "rls_enabled": bool(row[3]), "rls_forced": bool(row[4]),
                    "estimated_rows": int(row[5] or 0), "total_size": str(row[6]),
                    "columns": int(row[7] or 0),
                    "managed": str(row[0]) in self.MANAGED_APPLICATION_SCHEMAS,
                    "rls_manageable": str(row[0]) in self.RLS_MANAGED_SCHEMAS,
                } for row in cur.fetchall()]

    def describe_table(self, schema: str, table: str) -> dict[str, Any]:
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: conexão não configurada.", "db_password_missing")
        schema = self._validate_ident(schema)
        table = self._validate_ident(table)
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod),
                           NOT a.attnotnull AS nullable, pg_get_expr(ad.adbin, ad.adrelid) AS default_value,
                           EXISTS (
                             SELECT 1 FROM pg_catalog.pg_constraint pc
                             WHERE pc.conrelid=c.oid AND pc.contype='p' AND a.attnum = ANY(pc.conkey)
                           ) AS primary_key
                    FROM pg_catalog.pg_class c
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
                    LEFT JOIN pg_catalog.pg_attrdef ad ON ad.adrelid=c.oid AND ad.adnum=a.attnum
                    WHERE n.nspname=%s AND c.relname=%s AND c.relkind IN ('r','p')
                      AND a.attnum > 0 AND NOT a.attisdropped
                    ORDER BY a.attnum
                """, (schema, table))
                columns = [{
                    "name": str(r[0]), "type": str(r[1]), "nullable": bool(r[2]),
                    "default": "" if r[3] is None else str(r[3]), "primary_key": bool(r[4]),
                } for r in cur.fetchall()]
                if not columns:
                    raise ProviderError("Tabela PostgreSQL não encontrada.", "table_not_found")
                cur.execute("""
                    SELECT con.conname, con.contype, pg_get_constraintdef(con.oid, true)
                    FROM pg_catalog.pg_constraint con
                    JOIN pg_catalog.pg_class c ON c.oid=con.conrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname=%s AND c.relname=%s
                    ORDER BY con.contype, con.conname
                """, (schema, table))
                constraints = [{"name": str(r[0]), "type": str(r[1]), "definition": str(r[2])} for r in cur.fetchall()]
                cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_catalog.pg_indexes
                    WHERE schemaname=%s AND tablename=%s
                    ORDER BY indexname
                """, (schema, table))
                indexes = [{"name": str(r[0]), "definition": str(r[1])} for r in cur.fetchall()]
                cur.execute("""
                    SELECT policyname, permissive, roles, cmd, qual, with_check
                    FROM pg_catalog.pg_policies
                    WHERE schemaname=%s AND tablename=%s
                    ORDER BY policyname
                """, (schema, table))
                policies = [{
                    "name": str(r[0]), "permissive": str(r[1]), "roles": ", ".join(r[2] or []),
                    "command": str(r[3]), "using": "" if r[4] is None else str(r[4]),
                    "check": "" if r[5] is None else str(r[5]),
                } for r in cur.fetchall()]
        return {
            "schema": schema, "table": table, "managed": schema in self.MANAGED_APPLICATION_SCHEMAS,
            "columns": columns, "constraints": constraints, "indexes": indexes, "policies": policies,
        }

    def migration_status(self) -> dict[str, Any]:
        """Report the single current desired-state SQL snapshot.

        Historical migration fragments were consolidated into one idempotent
        schema artifact. The private ledger tracks the checksum of that current
        snapshot; unrelated historical ledger rows are intentionally ignored.
        """
        migration_path = self.root / "priv" / "supabase" / "migrations" / "000_current_schema.sql"
        if not migration_path.is_file():
            return {"ledger_exists": False, "ready": False, "migrations": []}
        expected_checksum = hashlib.sha256(migration_path.read_bytes()).hexdigest()
        applied: dict[str, str] | None = None
        ledger_exists = False
        if self.database_configured:
            try:
                with self._database_connection(connect_timeout=8) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT to_regclass('app_private.schema_migrations') IS NOT NULL")
                        ledger_exists = bool(cur.fetchone()[0])
                        if ledger_exists:
                            cur.execute(
                                "SELECT checksum_sha256, applied_at::text FROM app_private.schema_migrations WHERE migration=%s",
                                (migration_path.name,),
                            )
                            row = cur.fetchone()
                            if row:
                                applied = {"checksum": str(row[0]), "applied_at": str(row[1])}
            except Exception:
                ledger_exists = False
                applied = None
        if not ledger_exists or applied is None:
            state = "pending"
        elif applied["checksum"] != expected_checksum:
            state = "outdated"
        else:
            state = "applied"
        return {
            "ledger_exists": ledger_exists,
            "ready": state == "applied",
            "migrations": [{
                "migration": migration_path.name,
                "checksum": expected_checksum,
                "state": state,
                "applied_at": (applied or {}).get("applied_at", ""),
            }],
        }

    def application_schema_status(self, *, force: bool = False) -> dict[str, Any]:
        registration = self.registration_schema_status(force=force)
        if not self.database_configured:
            raise ProviderError("Cadastro indisponível: conexão de banco não configurada.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                      to_regclass('app_private.schema_migrations') IS NOT NULL,
                      to_regclass('app_private.email_delivery_events') IS NOT NULL,
                      to_regclass('public.friend_requests') IS NOT NULL,
                      to_regclass('public.guilds') IS NOT NULL,
                      to_regclass('public.guild_members') IS NOT NULL,
                      to_regclass('public.guild_channels') IS NOT NULL,
                      to_regclass('public.voice_sessions') IS NOT NULL,
                      to_regclass('public.voice_signals') IS NOT NULL
                """)
                row = cur.fetchone()
        checks = dict(registration.get("checks") or {})
        checks.update({
            "migration_ledger": bool(row and row[0]),
            "email_delivery_events": bool(row and row[1]),
            "friend_requests": bool(row and row[2]),
            "guilds": bool(row and row[3]),
            "guild_members": bool(row and row[4]),
            "guild_channels": bool(row and row[5]),
            "voice_sessions": bool(row and row[6]),
            "voice_signals": bool(row and row[7]),
        })
        return {"ready": all(checks.values()), "checks": checks}

    def ensure_application_schema(self) -> dict[str, Any]:
        status = self.application_schema_status(force=True)
        migration = self.migration_status()
        if status.get("ready") and migration.get("ready"):
            return {**status, "repaired": False, "migration": migration}
        report = self.apply_core_migration()
        self._registration_schema_cache = None
        self._registration_schema_cache_until = 0.0
        status = self.application_schema_status(force=True)
        migration = self.migration_status()
        if not status.get("ready") or not migration.get("ready"):
            raise ProviderError("As migrações foram executadas, mas a estrutura obrigatória continua incompleta.", "schema_not_ready")
        return {**status, "repaired": True, "migration": migration, "report": report}

    def registration_schema_status(self, *, force: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if not force and self._registration_schema_cache is not None and now < self._registration_schema_cache_until:
            return dict(self._registration_schema_cache)
        if not self.database_configured:
            raise ProviderError("Cadastro indisponível: conexão de banco não configurada.", "db_password_missing")
        try:
            import psycopg
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        sql = """
            SELECT
                to_regclass('public.profiles') IS NOT NULL AS profiles_table,
                EXISTS (
                    SELECT 1 FROM pg_catalog.pg_indexes
                    WHERE schemaname='public' AND tablename='profiles' AND indexname='profiles_username_unique'
                ) AS username_index,
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_constraint c
                    JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
                    WHERE n.nspname='public' AND t.relname='profiles' AND c.conname='profiles_username_format'
                ) AS username_format,
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_constraint c
                    JOIN pg_catalog.pg_class t ON t.oid=c.conrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
                    WHERE n.nspname='public' AND t.relname='profiles' AND c.conname='profiles_username_no_repeating_dots'
                ) AS no_repeating_dots,
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_trigger tg
                    JOIN pg_catalog.pg_class t ON t.oid=tg.tgrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
                    WHERE n.nspname='auth' AND t.relname='users'
                      AND tg.tgname='on_auth_user_created_profile' AND NOT tg.tgisinternal
                ) AS profile_trigger
        """
        try:
            with self._database_connection(connect_timeout=8) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    row = cur.fetchone()
            checks = {
                "profiles_table": bool(row and row[0]),
                "username_index": bool(row and row[1]),
                "username_format": bool(row and row[2]),
                "no_repeating_dots": bool(row and row[3]),
                "profile_trigger": bool(row and row[4]),
            }
            result = {"ready": all(checks.values()), "checks": checks}
            self._registration_schema_cache = result
            self._registration_schema_cache_until = now + (60.0 if result["ready"] else 10.0)
            return dict(result)
        except Exception as exc:
            self._registration_schema_cache = None
            self._registration_schema_cache_until = 0.0
            raise ProviderError("Não foi possível verificar a estrutura de cadastro.", "schema_check_failed", str(exc)) from exc

    def ensure_registration_schema(self) -> dict[str, Any]:
        # Compatibility entry point: v3.8 manages the complete application
        # schema, not a disconnected registration-only subset.
        return self.ensure_application_schema()

    def apply_core_migration(self) -> dict[str, Any]:
        """Apply the one current idempotent schema snapshot and record its checksum."""
        if not self.database_configured:
            raise ProviderError("Operação de banco negada: senha da conexão direta não configurada.", "db_password_missing")
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise ProviderError("Dependência psycopg não instalada.", "dependency_missing") from exc
        migration_path = self.root / "priv" / "supabase" / "migrations" / "000_current_schema.sql"
        if not migration_path.is_file():
            raise ProviderError("Snapshot SQL atual não encontrado.", "migration_missing")
        checksum = hashlib.sha256(migration_path.read_bytes()).hexdigest()
        sql = migration_path.read_text(encoding="utf-8")
        with self._database_connection(connect_timeout=8) as conn:
            with conn.cursor() as cur:
                # The snapshot creates the ledger before this UPSERT. Re-running
                # it is intentional: desired-state SQL repairs drift even when the
                # prior checksum already matched.
                cur.execute(sql)
                cur.execute(
                    """INSERT INTO app_private.schema_migrations(migration, checksum_sha256, applied_at)
                       VALUES(%s,%s,now())
                       ON CONFLICT (migration) DO UPDATE
                       SET checksum_sha256=excluded.checksum_sha256, applied_at=now()""",
                    (migration_path.name, checksum),
                )
            conn.commit()
        self._registration_schema_cache = None
        self._registration_schema_cache_until = 0.0
        return {"applied": [migration_path.name], "skipped": [], "total": 1, "checksum": checksum}

    def record_email_delivery_event(
        self, *, user_id: str | None, email: str, purpose: str, provider: str, outcome: str, provider_code: str = ""
    ) -> None:
        """Best-effort telemetry in the private Supabase application schema."""
        if not self.database_configured:
            return
        if purpose not in {"email_verification", "password_recovery", "magic_link", "test"}:
            return
        if provider not in {"supabase", "gmail"} or outcome not in {"requested", "sent", "failed"}:
            return
        try:
            import psycopg
            recipient_hash = hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()
            with self._database_connection(connect_timeout=4) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO app_private.email_delivery_events
                           (user_id, recipient_sha256, purpose, provider, outcome, provider_code)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        (user_id or None, recipient_hash, purpose, provider, outcome, (provider_code or "")[:128] or None),
                    )
                conn.commit()
        except Exception:
            # Delivery must not fail because telemetry is unavailable.
            return
