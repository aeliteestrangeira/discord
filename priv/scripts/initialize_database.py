from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "config" / ".env")
load_dotenv(ROOT / "config" / "SUPABASE_PRIVILEGED.env", override=False)

from lib.discord_app.security import KeyRing
from lib.discord_app.storage import ControlStore
from lib.discord_app.supabase_service import ProviderError, SupabaseService


def main() -> int:
    instance = ROOT / "instance"
    keys = KeyRing(instance)
    store = ControlStore(instance / "control.sqlite3", keys)
    provider = SupabaseService(store, ROOT)

    if not provider.database_configured:
        print("Banco direto não configurado: host/project ref/senha ausente.")
        return 2

    try:
        provider.apply_core_migration()
        store.set_secret("APP_DATABASE_SCHEMA_VERSION", "9", None)
        tables = provider.list_tables()
    except ProviderError as exc:
        store.add_audit(
            "system", "database-tool", "database.migration", "denied",
            target="current-schema-v9", details={"provider_code": exc.code},
        )
        print(f"Migração negada: {exc.public_message}")
        return 3
    except Exception as exc:
        store.add_audit(
            "system", "database-tool", "database.migration", "failure",
            target="current-schema-v9", details={"error_type": exc.__class__.__name__},
        )
        print(f"Falha ao inicializar o banco: {exc.__class__.__name__}")
        return 4

    store.add_audit(
        "system", "database-tool", "database.migration", "success",
        target="current-schema-v9", details={"table_count": len(tables)},
    )
    print("Migração base aplicada/verificada com sucesso.")
    print(f"Tabelas visíveis pela conexão direta: {len(tables)}")
    if any(row.get("schema") == "public" and row.get("table") == "profiles" for row in tables):
        print("OK: public.profiles encontrada.")
    else:
        print("ATENÇÃO: public.profiles não apareceu no inventário retornado.")
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
