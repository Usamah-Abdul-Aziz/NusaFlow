import time
import unittest

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import User, Workspace
from app.seed import ensure_demo_workspace, seed_database


class PasswordHashingTest(unittest.TestCase):
    def test_correct_password_verifies(self):
        hashed = hash_password("correct-horse-battery-staple")
        self.assertTrue(verify_password("correct-horse-battery-staple", hashed))

    def test_wrong_password_fails(self):
        hashed = hash_password("correct-horse-battery-staple")
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_hash_is_not_the_plaintext_password(self):
        hashed = hash_password("correct-horse-battery-staple")
        self.assertNotIn("correct-horse-battery-staple", hashed)

    def test_same_password_hashes_differently_each_time(self):
        # bcrypt salts automatically — two hashes of the same password
        # should never be identical, even though both verify correctly.
        first = hash_password("same-password")
        second = hash_password("same-password")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("same-password", first))
        self.assertTrue(verify_password("same-password", second))

    def test_malformed_hash_fails_closed(self):
        self.assertFalse(verify_password("anything", "not-a-real-bcrypt-hash"))


class TokenTest(unittest.TestCase):
    def test_token_round_trips_to_the_right_user_id(self):
        token = create_access_token(user_id=42)
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
        self.assertEqual(int(payload["sub"]), 42)

    def test_token_has_an_expiry_in_the_future(self):
        token = create_access_token(user_id=1)
        payload = jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])
        self.assertGreater(payload["exp"], payload["iat"])

    def test_token_signed_with_wrong_key_is_rejected(self):
        token = jwt.encode({"sub": "1", "iat": int(time.time()), "exp": int(time.time()) + 3600}, "wrong-secret", algorithm="HS256")
        with self.assertRaises(jwt.InvalidTokenError):
            jwt.decode(token, get_settings().SECRET_KEY, algorithms=["HS256"])


class AuthRoutesTest(unittest.TestCase):
    """API-level: signup, login, demo login, /me — via TestClient, same
    pattern as test_api_endpoints.py.
    """

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.TestSession = sessionmaker(bind=cls.engine)

        def override_get_db():
            db = cls.TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

        db = cls.TestSession()
        try:
            demo_workspace = ensure_demo_workspace(db)
            seed_database(db, demo_workspace.id)
        finally:
            db.close()

        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def test_signup_creates_a_new_empty_workspace(self):
        r = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "Acme Co", "display_name": "Jane", "email": "jane@acme.example", "password": "hunter22222"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("access_token", body)
        self.assertEqual(body["workspace"]["name"], "Acme Co")
        self.assertFalse(body["workspace"]["is_demo"])

        # New workspace should start with zero inventory — no auto-seeding.
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        inventory = self.client.get("/api/v1/inventory", headers=headers).json()
        self.assertEqual(inventory, [])

    def test_signup_duplicate_email_rejected(self):
        payload = {"workspace_name": "First", "display_name": "A", "email": "dup2@example.com", "password": "hunter22222"}
        self.client.post("/api/v1/auth/signup", json=payload)
        r = self.client.post(
            "/api/v1/auth/signup",
            json={**payload, "workspace_name": "Second"},
        )
        self.assertEqual(r.status_code, 409)

    def test_signup_password_too_short_rejected(self):
        r = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "X", "display_name": "X", "email": "short2@example.com", "password": "abc"},
        )
        self.assertEqual(r.status_code, 422)

    def test_signup_invalid_email_rejected(self):
        r = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "X", "display_name": "X", "email": "not-an-email", "password": "hunter22222"},
        )
        self.assertEqual(r.status_code, 422)

    def test_login_correct_credentials(self):
        self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "LoginCo", "display_name": "L", "email": "login2@example.com", "password": "hunter22222"},
        )
        r = self.client.post("/api/v1/auth/login", json={"email": "login2@example.com", "password": "hunter22222"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("access_token", r.json())

    def test_login_wrong_password_rejected(self):
        self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "LoginCo2", "display_name": "L", "email": "login3@example.com", "password": "hunter22222"},
        )
        r = self.client.post("/api/v1/auth/login", json={"email": "login3@example.com", "password": "wrong-password"})
        self.assertEqual(r.status_code, 401)

    def test_login_nonexistent_email_rejected_with_same_message_as_wrong_password(self):
        r1 = self.client.post("/api/v1/auth/login", json={"email": "nobody-here@example.com", "password": "whatever123"})
        self.assertEqual(r1.status_code, 401)

        self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "LoginCo3", "display_name": "L", "email": "login4@example.com", "password": "hunter22222"},
        )
        r2 = self.client.post("/api/v1/auth/login", json={"email": "login4@example.com", "password": "wrong-password"})
        # Same detail message whether the account exists or not — doesn't
        # let a caller enumerate which emails are registered.
        self.assertEqual(r1.json()["detail"], r2.json()["detail"])

    def test_demo_login_reaches_the_seeded_demo_workspace(self):
        r = self.client.post("/api/v1/auth/demo")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["workspace"]["is_demo"])

        headers = {"Authorization": f"Bearer {body['access_token']}"}
        inventory = self.client.get("/api/v1/inventory", headers=headers).json()
        self.assertEqual(len(inventory), 60)  # the full seeded demo dataset

    def test_demo_login_is_deterministic_same_account_every_time(self):
        first = self.client.post("/api/v1/auth/demo").json()
        second = self.client.post("/api/v1/auth/demo").json()
        self.assertEqual(first["user"]["id"], second["user"]["id"])
        self.assertEqual(first["workspace"]["id"], second["workspace"]["id"])

    def test_me_reflects_the_authenticated_user(self):
        signup = self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "MeCo", "display_name": "Casey", "email": "me2@example.com", "password": "hunter22222"},
        ).json()
        headers = {"Authorization": f"Bearer {signup['access_token']}"}
        r = self.client.get("/api/v1/auth/me", headers=headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["email"], "me2@example.com")
        self.assertEqual(r.json()["workspace"]["name"], "MeCo")

    def test_me_without_token_is_401(self):
        r = self.client.get("/api/v1/auth/me")
        self.assertEqual(r.status_code, 401)

    def test_password_is_never_stored_in_plaintext(self):
        self.client.post(
            "/api/v1/auth/signup",
            json={"workspace_name": "HashCo", "display_name": "H", "email": "hash2@example.com", "password": "hunter22222"},
        )
        db = self.TestSession()
        try:
            user = db.query(User).filter(User.email == "hash2@example.com").first()
            self.assertNotIn("hunter22222", user.password_hash)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
