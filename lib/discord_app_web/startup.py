from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.runtime import DATABASE_SCHEMA_VERSION, provider, store

def prepare_registration_schema_at_startup() -> None:
    """Verify/repair the allowlisted registration schema before serving traffic.

    A database outage must not take down login/admin entirely, so startup remains
    available while registration itself stays fail-closed through
    ``registration_schema_ready()``.
    """
    if not provider.database_configured:
        print("Cadastro: PostgreSQL não configurado; criação de contas permanecerá bloqueada.")
        return
    try:
        status = provider.ensure_application_schema()
        if status.get("ready"):
            if store.get_secret("APP_DATABASE_SCHEMA_VERSION") != DATABASE_SCHEMA_VERSION:
                store.set_secret("APP_DATABASE_SCHEMA_VERSION", DATABASE_SCHEMA_VERSION, None)
            repaired = " (reparado)" if status.get("repaired") else ""
            print(f"Aplicação: schema PostgreSQL/Supabase verificado{repaired}.")
            return
    except ProviderError as exc:
        print(f"Aplicação: schema PostgreSQL/Supabase indisponível [{exc.code}]; registro ficará bloqueado.")
        return
    print("Aplicação: schema PostgreSQL/Supabase incompleto; registro ficará bloqueado.")
