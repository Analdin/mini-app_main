import os
import tempfile
import unittest
from pathlib import Path

# Import the API with isolated local state. No real credentials or network calls.
_tmp = tempfile.TemporaryDirectory(prefix="alfadent-auth-test-")
os.environ["AUTH_DB_PATH"] = str(Path(_tmp.name) / "auth.sqlite3")
os.environ["BOT_DATA_DIR"] = str(Path(_tmp.name) / "telegram-data")
os.environ["TELEGRAM_TOKEN"] = "unit-test-telegram-token"
os.environ["MAX_BOT_TOKEN"] = "unit-test-max-token"
os.environ["INTERNAL_AUTH_SECRET"] = "unit-test-internal-secret"
os.environ["BITRIX24_WEBHOOK"] = ""

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

    def test_registration_stores_hash_and_returns_session(self):
        body = api.AuthBody(platform="telegram", phone="+7 988 233-77-25", name="Тест")
        result = api.auth_register(body, make_request(headers={
            "X-Internal-Auth": "unit-test-internal-secret"
        }))
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["password"]), 14)
        self.assertTrue(api._require_access(result["access_token"]))
        with api._auth_db() as conn:
            row = conn.execute(
                "SELECT password_hash FROM patient_accounts WHERE phone=?",
                ("+79882337725",),
            ).fetchone()
        self.assertNotEqual(row["password_hash"], result["password"].encode("utf-8"))
        self.assertNotEqual(row["password_hash"], result["password"])

    def test_existing_phone_cannot_be_registered_twice(self):
        body = api.AuthBody(platform="telegram", phone="+7 988 233-77-25")
        with self.assertRaises(HTTPException) as caught:
            api.auth_register(body, make_request(headers={
                "X-Internal-Auth": "unit-test-internal-secret"
            }))
        self.assertEqual(caught.exception.status_code, 409)

    def test_login_and_server_logout(self):
        body = api.AuthBody(
            platform="telegram",
            phone="+7 988 233-77-25",
            password="wrong-password",
        )
        with self.assertRaises(HTTPException) as caught:
            api.auth_login(body, make_request(headers={
                "X-Internal-Auth": "unit-test-internal-secret"
            }))
        self.assertEqual(caught.exception.status_code, 401)

        with api._auth_db() as conn:
            row = conn.execute(
                "SELECT password_salt FROM patient_accounts WHERE phone=?",
                ("+79882337725",),
            ).fetchone()
        correct_password = self._registered_password
        body.password = correct_password
        result = api.auth_login(body, make_request(headers={
            "X-Internal-Auth": "unit-test-internal-secret"
        }))
        token = result["access_token"]
        self.assertTrue(api._require_access(token))
        logout = api.auth_logout(make_request(headers={"Authorization": "Bearer " + token}))
        self.assertTrue(logout["logged_out"])
        with self.assertRaises(HTTPException):
            api._require_access(token)

    def setUp(self):
        self._registered_password = "unused"

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


if __name__ == "__main__":
    unittest.main()
