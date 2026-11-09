import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import quote, urlencode

# CI supplies a fake alfadent_config module from tests/fixtures.

from starlette.requests import Request
from fastapi import HTTPException
import webapp_api as api


def make_request(client_ip="127.0.0.1", headers=None):
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/test",
        "raw_path": b"/test",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_ip, 12345),
        "server": ("127.0.0.1", 8001),
    })


class AuthCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="alfadent-auth-case-")
        api.AUTH_DB_PATH = Path(self.tmp.name) / "auth.sqlite3"
        with api._auth_db() as conn:
            conn.execute("CREATE TABLE patient_accounts (phone TEXT PRIMARY KEY, password_salt BLOB NOT NULL, password_hash BLOB NOT NULL, display_name TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL)")
            conn.execute("CREATE TABLE patient_sessions (token_hash TEXT PRIMARY KEY, phone TEXT NOT NULL, expires_at REAL NOT NULL, created_at REAL NOT NULL)")
            conn.execute("CREATE TABLE auth_login_attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, phone TEXT NOT NULL, remote_ip TEXT NOT NULL, attempted_at REAL NOT NULL, success INTEGER NOT NULL DEFAULT 0)")
            conn.commit()

    def tearDown(self):
        self.tmp.cleanup()

    def internal_request(self):
        return make_request(headers={"X-Internal-Auth": "unit-test-internal-secret"})

    def register(self):
        return api.auth_register(
            api.AuthBody(platform="telegram", phone="+7 988 233-77-25", name="Тест"),
            self.internal_request(),
        )

    def test_russian_phone_normalization(self):
        self.assertEqual(api._phone("+7 (988) 233-77-25"), "+79882337725")
        self.assertEqual(api._phone("8 988 233-77-25"), "+79882337725")
        with self.assertRaises(HTTPException):
            api._phone("12345")

    def test_password_hash_uses_unique_salt(self):
        first = api._password_hash("example-password", b"a" * 16)
        same_salt = api._password_hash("example-password", b"a" * 16)
        other_salt = api._password_hash("example-password", b"b" * 16)
        self.assertEqual(first, same_salt)
        self.assertNotEqual(first, other_salt)
        self.assertEqual(len(first), 32)

    def test_registration_stores_hash_and_returns_session(self):
        result = self.register()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["password"]), 14)
        self.assertTrue(api._require_access(result["access_token"]))
        with api._auth_db() as conn:
            row = conn.execute(
                "SELECT password_salt,password_hash FROM patient_accounts WHERE phone=?",
                ("+79882337725",),
            ).fetchone()
        self.assertEqual(len(row["password_salt"]), 16)
        self.assertEqual(len(row["password_hash"]), 32)
        self.assertNotEqual(row["password_hash"], result["password"].encode("utf-8"))

    def test_existing_phone_cannot_be_registered_twice(self):
        self.register()
        with self.assertRaises(HTTPException) as caught:
            self.register()
        self.assertEqual(caught.exception.status_code, 409)

    def test_login_and_server_logout(self):
        registered = self.register()
        body = api.AuthBody(
            platform="telegram",
            phone="+7 988 233-77-25",
            password="wrong-password",
        )
        with self.assertRaises(HTTPException) as caught:
            api.auth_login(body, self.internal_request())
        self.assertEqual(caught.exception.status_code, 401)

        body.password = registered["password"]
        result = api.auth_login(body, self.internal_request())
        token = result["access_token"]
        self.assertTrue(result["authorized"])
        self.assertTrue(api._require_access(token))
        logout = api.auth_logout(make_request(headers={"Authorization": "Bearer " + token}))
        self.assertTrue(logout["logged_out"])
        with self.assertRaises(HTTPException):
            api._require_access(token)

    def test_internal_secret_is_local_only(self):
        body = api.AuthBody(platform="telegram", phone="+7 988 233-77-25")
        with self.assertRaises(HTTPException) as caught:
            api._auth_identity(
                body,
                make_request(
                    client_ip="192.0.2.10",
                    headers={"X-Internal-Auth": "unit-test-internal-secret"},
                ),
            )
        self.assertEqual(caught.exception.status_code, 401)

    def signed_init_data(self, token, platform="telegram", auth_date=None):
        fields = {
            "auth_date": str(auth_date if auth_date is not None else int(time.time())),
            "user": json.dumps(
                {"id": 123456, "first_name": "Unit Test"},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
        fields["hash"] = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return urlencode(fields, quote_via=quote)

    def test_telegram_init_data_signature(self):
        signed = self.signed_init_data(api.BOT_TOKEN)
        user = api.validated_telegram_user(signed)
        self.assertEqual(user["id"], 123456)

        tampered = signed.replace("123456", "654321")
        with self.assertRaises(HTTPException) as caught:
            api.validated_telegram_user(tampered)
        self.assertEqual(caught.exception.status_code, 401)

    def test_max_init_data_signature(self):
        signed = self.signed_init_data(api.MAX_BOT_TOKEN, platform="max")
        user = api.validated_max_user(signed)
        self.assertEqual(user["id"], 123456)

        tampered = signed.replace("123456", "654321")
        with self.assertRaises(HTTPException) as caught:
            api.validated_max_user(tampered)
        self.assertEqual(caught.exception.status_code, 401)

    def test_stale_init_data_is_rejected(self):
        stale = self.signed_init_data(api.BOT_TOKEN, auth_date=int(time.time()) - 7200)
        with self.assertRaises(HTTPException) as caught:
            api.validated_telegram_user(stale)
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
