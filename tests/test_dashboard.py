import unittest
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError

from dashboard import (
    BalanceSetRequest,
    _csrf_token,
    _has_discord_administrator_permission,
    _session_cookie_options,
    _signed_state,
    _verify_state,
)


class DashboardSecurityTests(unittest.TestCase):
    def test_oauth_state_round_trip_and_rejects_mismatch(self):
        cookie = _signed_state("state-value", "pkce-verifier", "a" * 40)
        self.assertEqual(_verify_state(cookie, "state-value", "a" * 40), "pkce-verifier")
        with self.assertRaises(HTTPException):
            _verify_state(cookie, "different-state", "a" * 40)

    def test_oauth_state_rejects_tampering(self):
        cookie = _signed_state("state-value", "pkce-verifier", "a" * 40)
        tampered = cookie[:-1] + ("A" if cookie[-1] != "A" else "B")
        with self.assertRaises(HTTPException):
            _verify_state(tampered, "state-value", "a" * 40)

    def test_csrf_token_is_bound_to_session_token(self):
        self.assertNotEqual(_csrf_token("session-a"), _csrf_token("session-b"))
        self.assertEqual(len(_csrf_token("session-a")), 64)

    def test_admin_permission_comes_from_owner_or_assigned_admin_role(self):
        guild = {"owner_id": "100"}
        self.assertTrue(_has_discord_administrator_permission(100, guild, {"roles": []}, []))
        self.assertTrue(
            _has_discord_administrator_permission(
                200,
                guild,
                {"roles": ["10"]},
                [{"id": "10", "permissions": str(1 << 3)}],
            )
        )
        self.assertFalse(
            _has_discord_administrator_permission(
                200,
                guild,
                {"roles": ["10"]},
                [{"id": "10", "permissions": "0"}],
            )
        )

    def test_cross_site_sessions_require_secure_none_cookie(self):
        self.assertEqual(
            _session_cookie_options("https://api.example.com", "https://app.example.net"),
            {"secure": True, "samesite": "none"},
        )
        self.assertEqual(
            _session_cookie_options("http://localhost:8000", "http://localhost:3000"),
            {"secure": False, "samesite": "lax"},
        )

    def test_balance_set_requires_nonnegative_cent_precision_and_reason(self):
        payload = BalanceSetRequest(account_type="wallet", balance="123.45", reason="  correction  ")
        self.assertEqual(payload.balance, Decimal("123.45"))
        self.assertEqual(payload.reason, "correction")
        for invalid in (
            {"account_type": "wallet", "balance": "-1.00", "reason": "reason"},
            {"account_type": "wallet", "balance": "1.001", "reason": "reason"},
            {"account_type": "wallet", "balance": "1.00", "reason": "   "},
        ):
            with self.subTest(payload=invalid), self.assertRaises(ValidationError):
                BalanceSetRequest(**invalid)


if __name__ == "__main__":
    unittest.main()
