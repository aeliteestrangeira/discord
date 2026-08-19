from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class FakeStore:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.audit: list[dict] = []

    def get_secret(self, name: str):
        return self.values.get(name)

    def set_secret(self, name: str, value: str, admin_id):
        self.values[name] = value

    def add_audit(self, *args, **kwargs):
        self.audit.append({"args": args, "kwargs": kwargs})


def load_bootstrap_module():
    fake_storage = types.ModuleType("lib.discord_app.storage")
    fake_storage.ControlStore = FakeStore
    previous = sys.modules.get("lib.discord_app.storage")
    sys.modules["lib.discord_app.storage"] = fake_storage
    try:
        spec = importlib.util.spec_from_file_location("lib.discord_app.bootstrap_preservation_test", ROOT / "lib" / "discord_app" / "bootstrap.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("lib.discord_app.storage", None)
        else:
            sys.modules["lib.discord_app.storage"] = previous


class BootstrapCredentialPreservationTests(unittest.TestCase):
    def test_bootstrap_import_preserves_source_files_byte_for_byte(self):
        bootstrap = load_bootstrap_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / ".env"
            privileged_path = root / "SUPABASE_PRIVILEGED.env"
            env_bytes = (
                b"SUPABASE_URL=https://abcdefgh.supabase.co\n"
                b"SUPABASE_PUBLISHABLE_KEY=sb_publishable_DUMMY_FOR_TEST_ONLY\n"
                b"SUPABASE_PROJECT_REF=abcdefgh\n"
                b"SUPABASE_DB_HOST=db.abcdefgh.supabase.co\n"
                b"SUPABASE_DB_PASSWORD=dummy-db-password\n"
                b"HCAPTCHA_SITE_KEY=10000000-ffff-ffff-ffff-000000000001\n"
            )
            privileged_bytes = (
                b"SUPABASE_SECRET_KEY=sb_secret_DUMMY_FOR_TEST_ONLY\n"
                b"SUPABASE_SERVICE_ROLE_KEY=dummy.header.signature\n"
                b"HCAPTCHA_SECRET=0xDUMMY-HCAPTCHA-SECRET\n"
            )
            env_path.write_bytes(env_bytes)
            privileged_path.write_bytes(privileged_bytes)
            values = {
                "SUPABASE_URL": "https://abcdefgh.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_DUMMY_FOR_TEST_ONLY",
                "SUPABASE_PROJECT_REF": "abcdefgh",
                "SUPABASE_DB_HOST": "db.abcdefgh.supabase.co",
                "SUPABASE_DB_PASSWORD": "dummy-db-password",
                "SUPABASE_SECRET_KEY": "sb_secret_DUMMY_FOR_TEST_ONLY",
                "SUPABASE_SERVICE_ROLE_KEY": "dummy.header.signature",
                "HCAPTCHA_SITE_KEY": "10000000-ffff-ffff-ffff-000000000001",
                "HCAPTCHA_SECRET": "0xDUMMY-HCAPTCHA-SECRET",
            }
            store = FakeStore()
            with mock.patch.dict(os.environ, values, clear=True):
                stored = bootstrap.migrate_bootstrap_env(root, store)

            self.assertEqual(env_path.read_bytes(), env_bytes)
            self.assertEqual(privileged_path.read_bytes(), privileged_bytes)
            self.assertEqual(set(stored), set(values))
            self.assertEqual(store.values, values)

    def test_existing_encrypted_value_wins_without_mutating_bootstrap(self):
        bootstrap = load_bootstrap_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_path = root / ".env"
            original = b"SUPABASE_URL=https://abcdefgh.supabase.co\n"
            env_path.write_bytes(original)
            store = FakeStore()
            store.values["SUPABASE_URL"] = "https://existing.supabase.co"

            with mock.patch.dict(os.environ, {"SUPABASE_URL": "https://abcdefgh.supabase.co"}, clear=True):
                stored = bootstrap.migrate_bootstrap_env(root, store)

            self.assertEqual(stored, [])
            self.assertEqual(store.get_secret("SUPABASE_URL"), "https://existing.supabase.co")
            self.assertEqual(env_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
