from __future__ import annotations

import getpass
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.discord_app.bootstrap import BOOTSTRAP_KEYS, migrate_bootstrap_env
from lib.discord_app.security import KeyRing
from lib.discord_app.storage import ControlStore
from lib.discord_app.supabase_service import ProviderError, SupabaseService
from lib.discord_app.validators import ValidationError, validate_password_strength


USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
def main() -> int:
    env_path = ROOT / ".env"
    load_dotenv(env_path)
    load_dotenv(ROOT / "config" / ".env")
    load_dotenv(ROOT / "config" / "SUPABASE_PRIVILEGED.env", override=False)

    print("Instalação do administrador local")
    print("O usuário não é criado no provedor remoto; ele protege o plano de controle desta máquina.")
    username = input("Usuário administrativo: ").strip().lower()
    if not USERNAME_RE.fullmatch(username):
        print("Usuário inválido. Use 3-64 caracteres: letras, números, ponto, hífen ou sublinhado.")
        return 2

    password = getpass.getpass("Senha administrativa (mínimo 16 caracteres): ")
    confirm = getpass.getpass("Confirme a senha: ")
    if password != confirm:
        print("As senhas não coincidem.")
        return 2
    try:
        password = validate_password_strength(password, username=username, field="Senha administrativa")
    except ValidationError as exc:
        print(str(exc))
        return 2

    instance = ROOT / "instance"
    keys = KeyRing(instance)
    store = ControlStore(instance / "control.sqlite3", keys)
    admin_id = store.create_or_replace_admin(username, password)

    bootstrapped = migrate_bootstrap_env(ROOT, store)

    database_status = "not_configured"
    provider = SupabaseService(store, ROOT)
    if provider.database_configured:
        try:
            provider.apply_core_migration()
            store.set_secret("APP_DATABASE_SCHEMA_VERSION", "8", None)
            database_status = "applied"
            store.add_audit(
                "system",
                "installer",
                "database.migration",
                "success",
                target="core-migrations-v8",
                details={"mode": "install"},
            )
        except ProviderError as exc:
            database_status = f"denied:{exc.code}"
            store.add_audit(
                "system",
                "installer",
                "database.migration",
                "denied",
                target="core-migrations-v8",
                details={"provider_code": exc.code, "mode": "install"},
            )
        except Exception as exc:
            database_status = f"failure:{exc.__class__.__name__}"
            store.add_audit(
                "system",
                "installer",
                "database.migration",
                "failure",
                target="core-migrations-v8",
                details={"error_type": exc.__class__.__name__, "mode": "install"},
            )

    store.add_audit(
        "system",
        "installer",
        "admin.install",
        "success",
        target=str(admin_id),
        details={"username": username, "bootstrap_config_moved": bootstrapped, "database_status": database_status},
    )
    print(f"Administrador '{username}' instalado/atualizado com sucesso.")
    print("As sessões administrativas anteriores desse usuário foram revogadas.")
    if bootstrapped:
        print("Configuração bootstrap copiada para o armazenamento local criptografado.")
        print("O arquivo bootstrap de origem foi preservado intencionalmente para facilitar atualizações.")
    print("O administrador usa a mesma página login.html dos demais usuários.")
    if database_status == "applied":
        print("Migração base do banco aplicada/verificada com sucesso.")
    elif provider.database_configured:
        print(f"ATENÇÃO: a migração base do banco não foi aplicada ({database_status}).")
        print("Use INITIALIZE_DATABASE.bat ou a tela /admin/tables após corrigir conectividade/configuração.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
