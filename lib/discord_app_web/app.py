from __future__ import annotations

import argparse
import os
from pathlib import Path

from flask import Flask

from lib.discord_app_web.errors import register_error_handlers
from lib.discord_app_web.router import register_routes
from lib.discord_app_web.runtime import APP_HOSTNAME, INSTANCE_DIR, store
from lib.discord_app_web.security import register_security_hooks
from lib.discord_app_web.startup import prepare_registration_schema_at_startup


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent / "templates"), static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=9 * 1024 * 1024, JSON_SORT_KEYS=False)
    register_security_hooks(app)
    register_routes(app)
    register_error_handlers(app)
    return app


app = create_app()


def run() -> None:
    parser = argparse.ArgumentParser(description="Servidor Flask local.")
    parser.add_argument("--bind", default=os.getenv("FLASK_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FLASK_PORT", "8000")))
    parser.add_argument("--tls-cert", default=str(INSTANCE_DIR / "tls" / "server-cert.pem"))
    parser.add_argument("--tls-key", default=str(INSTANCE_DIR / "tls" / "server-key.pem"))
    parser.add_argument("--instance-marker", default="", help=argparse.SUPPRESS)
    args = parser.parse_args()

    store.cleanup()
    prepare_registration_schema_at_startup()
    cert_path = Path(args.tls_cert).resolve()
    key_path = Path(args.tls_key).resolve()
    if not cert_path.is_file() or not key_path.is_file():
        raise RuntimeError("Certificado TLS local ausente. Execute SERVER.bat para preparar o HTTPS local.")

    print(f"Login único HTTPS: https://{APP_HOSTNAME}:{args.port}/")
    print(f"Controle protegido HTTPS: https://{APP_HOSTNAME}:{args.port}/admin")
    app.run(
        host=args.bind, port=args.port, debug=False, threaded=True, use_reloader=False,
        ssl_context=(str(cert_path), str(key_path)),
    )


if __name__ == "__main__":
    run()
