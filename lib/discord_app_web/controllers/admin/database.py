from typing import Any
from flask import abort, redirect, render_template, request, url_for
from lib.discord_app.security import sha256_text
from lib.discord_app.supabase_service import ProviderError
from lib.discord_app_web.runtime import DATABASE_SCHEMA_VERSION, provider, store
from lib.discord_app_web.security import admin_csrf_token, admin_identity, admin_required, audit, require_admin_csrf

def admin_tables():
    _, username = admin_identity()
    message = None
    error = None
    selected_schema = (request.values.get("schema") or "public").strip()
    selected_table = (request.values.get("table") or "").strip()
    if request.method == "POST":
        require_admin_csrf()
        action = request.form.get("action", "")
        if action == "apply-core-migration":
            if request.form.get("confirm") != "APLICAR":
                error = "Confirmação inválida."
            else:
                try:
                    report = provider.apply_core_migration()
                    status = provider.ensure_application_schema()
                    store.set_secret("APP_DATABASE_SCHEMA_VERSION", DATABASE_SCHEMA_VERSION, None)
                    audit(
                        "admin", username, "database.migration", "success", target="current-schema-v9",
                        details={"applied": report.get("applied", []), "skipped": report.get("skipped", []), "ready": bool(status.get("ready"))},
                    )
                    message = f"Migrações verificadas: {len(report.get('applied', []))} aplicada(s), {len(report.get('skipped', []))} já vigente(s)."
                except ProviderError as exc:
                    audit("admin", username, "database.migration", "denied", target="current-schema-v9", details={"provider_code": exc.code})
                    error = exc.public_message
                except Exception as exc:
                    audit("admin", username, "database.migration", "failure", target="current-schema-v9", details={"error_type": exc.__class__.__name__})
                    error = "Falha ao aplicar as migrações."
        else:
            abort(400)

    schemas: list[str] = []
    tables: list[dict[str, Any]] = []
    table_detail: dict[str, Any] | None = None
    db_health: dict[str, str] | None = None
    migration_status: dict[str, Any] = {"ready": False, "ledger_exists": False, "migrations": []}
    local_tables = store.list_local_tables()
    if provider.database_configured:
        try:
            schemas = provider.list_schemas()
            if selected_schema not in schemas:
                selected_schema = "public" if "public" in schemas else (schemas[0] if schemas else "public")
            tables = provider.list_tables(selected_schema)
            if selected_table and any(item["table"] == selected_table for item in tables):
                table_detail = provider.describe_table(selected_schema, selected_table)
            db_health = provider.database_health()
            migration_status = provider.migration_status()
            audit("admin", username, "database.table_list", "success", details={"count": len(tables), "schema": selected_schema})
        except Exception as exc:
            audit("admin", username, "database.table_list", "failure", details={"error_type": exc.__class__.__name__, "schema": selected_schema})
            error = error or "Não foi possível consultar as tabelas reais do Supabase."

    return render_template(
        "admin/tables.html",
        username=username,
        csrf=admin_csrf_token(),
        tables=tables,
        schemas=schemas,
        selected_schema=selected_schema,
        selected_table=selected_table,
        table_detail=table_detail,
        database_configured=provider.database_configured,
        db_health=db_health,
        project_ref=provider.project_ref,
        db_host=provider.db_host,
        migration_status=migration_status,
        local_tables=local_tables,
        message=message,
        error=error,
    )

def admin_table_rls():
    require_admin_csrf()
    _, username = admin_identity()
    schema = (request.form.get("schema") or "").strip()
    table = (request.form.get("table") or "").strip()
    mode = request.form.get("mode", "enable")
    if request.form.get("confirm") != "ATIVAR" or mode not in {"enable", "force"}:
        audit("admin", username, "database.rls", "denied", target=f"{schema}.{table}", details={"reason": "confirmation"})
        return redirect(url_for("admin_tables", schema=schema, table=table))
    try:
        provider.enable_rls(schema, table, force=(mode == "force"))
        audit("admin", username, "database.rls", "success", target=f"{schema}.{table}", details={"mode": mode})
    except ProviderError as exc:
        audit("admin", username, "database.rls", "denied", target=f"{schema}.{table}", details={"provider_code": exc.code})
    except Exception as exc:
        audit("admin", username, "database.rls", "failure", target=f"{schema}.{table}", details={"error_type": exc.__class__.__name__})
    return redirect(url_for("admin_tables", schema=schema, table=table))

def admin_sql():
    _, username = admin_identity()
    result = None
    error = None
    sql_text = ""
    mode = "read"
    if request.method == "POST":
        require_admin_csrf()
        sql_text = request.form.get("sql") or ""
        mode = request.form.get("mode", "read")
        allow_write = mode == "write"
        if allow_write and request.form.get("confirm") != "EXECUTAR":
            audit("admin", username, "database.sql", "denied", target=sha256_text(sql_text), details={"reason": "confirmation", "mode": mode})
            error = "Confirmação inválida para comando de alteração."
        else:
            try:
                result = provider.execute_sql(sql_text, allow_write=allow_write)
                audit("admin", username, "database.sql", "success", target=sha256_text(sql_text), details={"keyword": result.get("keyword"), "mode": mode, "rowcount": result.get("rowcount"), "duration_ms": result.get("duration_ms")})
            except ProviderError as exc:
                audit("admin", username, "database.sql", "denied", target=sha256_text(sql_text), details={"provider_code": exc.code, "mode": mode})
                error = exc.public_message
            except Exception as exc:
                audit("admin", username, "database.sql", "failure", target=sha256_text(sql_text), details={"error_type": exc.__class__.__name__, "mode": mode})
                error = "Falha ao executar o comando."
    db_health = None
    if provider.database_configured:
        try:
            db_health = provider.database_health()
        except Exception:
            db_health = None
    return render_template(
        "admin/sql.html",
        username=username, csrf=admin_csrf_token(), database_configured=provider.database_configured,
        result=result, error=error, sql_text=sql_text, mode=mode,
        project_ref=provider.project_ref, db_host=provider.db_host, db_health=db_health,
    )


def register_routes(app) -> None:
    app.add_url_rule("/admin/tables", view_func=admin_required(admin_tables), methods=["GET", "POST"])
    app.add_url_rule("/admin/tables/rls", view_func=admin_required(admin_table_rls), methods=["POST"])
    app.add_url_rule("/admin/sql", view_func=admin_required(admin_sql), methods=["GET", "POST"])
