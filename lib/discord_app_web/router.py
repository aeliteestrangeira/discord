from __future__ import annotations

from lib.discord_app_web.controllers import assets, auth, friends, guilds, pages, voice
from lib.discord_app_web.controllers.admin import audit, cloudinary, config, database, session, users

ROUTE_MODULES = (
    pages, guilds, voice, auth, friends,
    session, config, cloudinary, users, database, audit,
    assets,
)

def register_routes(app) -> None:
    for module in ROUTE_MODULES:
        module.register_routes(app)
