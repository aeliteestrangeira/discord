from __future__ import annotations

import os
import unittest
from unittest import mock

from lib.discord_app.hcaptcha_service import HCaptchaService
from lib.discord_app.validators import ValidationError, validate_password_strength, validate_registration


class FakeSecretStore:
    def __init__(self):
        self.values = {}

    def get_secret(self, name: str):
        return self.values.get(name)


class PasswordPolicyTests(unittest.TestCase):
    def test_short_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_password_strength("short-password")

    def test_long_low_diversity_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_password_strength("a" * 24)

    def test_identity_containing_password_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_password_strength("alice-very-long-passphrase", email="alice@example.com")

    def test_strong_passphrase_is_accepted(self):
        value = "Cedar!Orbit7-Lantern_River"
        self.assertEqual(validate_password_strength(value), value)

    def test_registration_enforces_shared_policy(self):
        payload = {
            "email": "user@example.com",
            "password": "Cedar!Orbit7-Lantern_River",
            "profile": {
                "username": "person.7",
                "date_of_birth": "1995-02-03",
            },
        }
        email, password, metadata = validate_registration(payload)
        self.assertEqual(email, "user@example.com")
        self.assertEqual(password, payload["password"])
        self.assertEqual(metadata["username"], "person.7")


class HCaptchaVerificationTests(unittest.TestCase):
    def _service(self):
        store = FakeSecretStore()
        store.values["HCAPTCHA_SITE_KEY"] = "2762416e-5212-485e-919e-5c580ba6f606"
        store.values["HCAPTCHA_SECRET"] = "ES_" + "a" * 32
        return HCaptchaService(store)

    def _verify_payload(self, payload: bytes):
        service = self._service()

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return payload

        with mock.patch("urllib.request.urlopen", return_value=Response()):
            return service.verify("token", "127.0.0.1")

    def test_siteverify_success_is_authoritative_and_hostname_is_audited(self):
        result = self._verify_payload(b'{"success":true,"hostname":"discord","error-codes":[]}')
        self.assertTrue(result.success)
        self.assertEqual(result.hostname, "discord")
        self.assertEqual(result.error_codes, ())

    def test_siteverify_success_without_hostname_is_not_locally_denied(self):
        result = self._verify_payload(b'{"success":true,"error-codes":[]}')
        self.assertTrue(result.success)
        self.assertEqual(result.hostname, "")

    def test_siteverify_success_with_different_reported_hostname_is_not_overridden(self):
        # Host authorization belongs to the Flask Host allowlist and provider-side
        # hCaptcha domain policy.  The returned hostname remains diagnostic only.
        legacy = "discord" + ".local" + ".test"
        payload = ('{"success":true,"hostname":"%s","error-codes":[]}' % legacy).encode()
        result = self._verify_payload(payload)
        self.assertTrue(result.success)
        self.assertEqual(result.hostname, legacy)

    def test_siteverify_provider_denial_is_preserved(self):
        result = self._verify_payload(b'{"success":false,"error-codes":["invalid-input-response"]}')
        self.assertFalse(result.success)
        self.assertIn("invalid-input-response", result.error_codes)


if __name__ == "__main__":
    unittest.main()
