from . import login, passkey, registration, security, session

MODULES = (security, passkey, login, registration, session)

def register_routes(app) -> None:
    for module in MODULES:
        module.register_routes(app)
