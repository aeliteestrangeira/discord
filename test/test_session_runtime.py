from __future__ import annotations

import threading
import time
import tempfile
import unittest
from pathlib import Path

from lib.discord_app.security import KeyRing
from lib.discord_app.session_authority import SessionAuthority


class FakeStore:
    def __init__(self):
        self.revoked = []

    def delete_browser_sessions_for_user(self, user_id):
        self.revoked.append(user_id)
        return 2


class FakeProvider:
    def __init__(self, exists=True, delay=0.0):
        self.exists = exists
        self.delay = delay
        self.calls = 0
        self.lock = threading.Lock()

    def auth_user_exists_by_id(self, user_id):
        with self.lock:
            self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.exists


class SessionAuthorityTests(unittest.TestCase):
    def test_single_flight_coalesces_concurrent_identity_checks(self):
        store = FakeStore()
        provider = FakeProvider(exists=True, delay=0.05)
        authority = SessionAuthority(store, provider, lease_seconds=0.75)
        results = []
        threads = [threading.Thread(target=lambda: results.append(authority.user_exists("a" * 36))) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(results, [True] * 12)
        self.assertEqual(provider.calls, 1)

    def test_short_lease_reuses_recent_result_and_force_refreshes(self):
        provider = FakeProvider(exists=True)
        authority = SessionAuthority(FakeStore(), provider, lease_seconds=0.75)
        self.assertTrue(authority.user_exists("b" * 36))
        self.assertTrue(authority.user_exists("b" * 36))
        self.assertEqual(provider.calls, 1)
        self.assertTrue(authority.user_exists("b" * 36, force=True))
        self.assertEqual(provider.calls, 2)


    def test_presence_companion_is_bound_and_domain_separated_from_csrf(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = KeyRing(Path(tmp))
            token = "opaque-session-token"
            presence = keys.presence_for_session(token)
            self.assertEqual(presence, keys.presence_for_session(token))
            self.assertNotEqual(presence, keys.presence_for_session(token + "-other"))
            self.assertNotEqual(presence, keys.csrf_for_session(token))

    def test_revoke_invalidates_lease_and_all_local_sessions(self):
        store = FakeStore()
        provider = FakeProvider(exists=True)
        authority = SessionAuthority(store, provider)
        authority.observe("c" * 36, True)
        self.assertEqual(authority.revoke_user("c" * 36), 2)
        self.assertEqual(store.revoked, ["c" * 36])
        self.assertTrue(authority.user_exists("c" * 36))
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
