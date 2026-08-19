from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .supabase_service import SupabaseService
    from .storage import ControlStore


@dataclass(frozen=True, slots=True)
class IdentityLease:
    exists: bool
    checked_at: float


class SessionAuthority:
    """Single authority for live Supabase-principal validation.

    This mirrors the reviewed Elixir AuthSession + RequireAppAuth boundary: the
    browser never decides whether an Actor is still valid. A short positive/
    negative lease removes redundant database round trips, while a per-user
    single-flight gate ensures concurrent UI requests share one authority check
    rather than opening duplicate checks for the same principal.
    """

    def __init__(self, store: "ControlStore", provider: "SupabaseService", lease_seconds: float = 0.75):
        self.store = store
        self.provider = provider
        self.lease_seconds = max(0.25, float(lease_seconds))
        self._lock = threading.RLock()
        self._leases: dict[str, IdentityLease] = {}
        self._inflight: dict[str, threading.Event] = {}

    def observe(self, user_id: str, exists: bool) -> None:
        value = (user_id or "").strip()
        if not value:
            return
        with self._lock:
            self._leases[value] = IdentityLease(exists=bool(exists), checked_at=time.monotonic())

    def user_exists(self, user_id: str, *, force: bool = False) -> bool:
        user_id = (user_id or "").strip()
        if not user_id:
            return False

        while True:
            now = time.monotonic()
            leader = False
            with self._lock:
                lease = self._leases.get(user_id)
                if not force and lease and now - lease.checked_at < self.lease_seconds:
                    return lease.exists
                event = self._inflight.get(user_id)
                if event is None:
                    event = threading.Event()
                    self._inflight[user_id] = event
                    leader = True

            if leader:
                try:
                    exists = bool(self.provider.auth_user_exists_by_id(user_id))
                    self.observe(user_id, exists)
                    return exists
                finally:
                    with self._lock:
                        current = self._inflight.pop(user_id, None)
                        if current is not None:
                            current.set()

            # Another request is already validating this exact Actor. Wait for
            # that result instead of generating another database round trip.
            event.wait(timeout=3.0)
            force = False

    def invalidate(self, user_id: str) -> None:
        with self._lock:
            self._leases.pop((user_id or "").strip(), None)

    def revoke_user(self, user_id: str) -> int:
        value = (user_id or "").strip()
        self.invalidate(value)
        return self.store.delete_browser_sessions_for_user(value)
