"""Offline identity-bound access codes and revocable, expiring bearer sessions.

The server creates its own private key and account-bound codes. An explicit
local demo mode lets a jury use two fixed synthetic accounts without a code.
Both entry points issue the same revocable sessions; permissions stay enforced.
"""

import argparse
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from backend.loader import database_path
from backend.store import Store


SESSION_SECONDS = 8 * 60 * 60
DEMO_EMPLOYEE_ID = "E0002"
bearer = HTTPBearer(auto_error=False)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=220)
    access_code: str = Field(min_length=1, max_length=200)


class DemoLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account: Literal["employee", "hr"]


def canonical_username(username):
    username = username.strip()
    if username.lower() == "hr":
        return "hr"
    if username.lower().startswith("employee:"):
        return "employee:" + username[len("employee:"):]
    return "employee:" + username


class Auth:
    def __init__(self, store):
        self.store = store
        self.demo_enabled = (
            os.environ.get("AUTH_DEMO_MODE", "").strip().lower() in {"true", "1", "yes"}
            and os.environ.get("APP_ENV") == "local"
        )
        key_path = Path(store.path + ".auth-key")
        # The SQLite write lock serializes first starts before publishing the key.
        with store.transaction(write=True) as connection:
            if not key_path.exists():
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(secrets.token_bytes(32))
            self.key = key_path.read_bytes()
            if len(self.key) != 32:
                raise ValueError("Invalid local authentication key; restore the original key file")
            connection.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL,
                employee_id TEXT, expires_at REAL NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0)""")
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(auth_sessions)")}
            if "is_demo" not in columns:
                connection.execute("ALTER TABLE auth_sessions ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
            connection.execute("""CREATE TABLE IF NOT EXISTS auth_attempts (
                username TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL)""")

    def identity(self, username):
        username = canonical_username(username)
        if username == "hr":
            return {"username": "hr", "role": "hr", "employee_id": None}
        if username.startswith("employee:"):
            employee_id = username.removeprefix("employee:")
            with self.store.transaction() as connection:
                if connection.execute("SELECT 1 FROM employees WHERE employee_id = ?", (employee_id,)).fetchone():
                    return {"username": username, "role": "employee", "employee_id": employee_id}
        return None

    def credentials(self, username):
        username = canonical_username(username)
        if self.identity(username) is None:
            raise ValueError("Unknown account; use hr or an employee ID such as E0002")
        return {"username": username, "access_code": hmac.new(
            self.key, ("career-quest-login:" + username).encode(), hashlib.sha256
        ).hexdigest()[:10].upper()}

    def demo_status(self):
        employee_id = DEMO_EMPLOYEE_ID if self.demo_enabled and self.identity(DEMO_EMPLOYEE_ID) else None
        return {"enabled": self.demo_enabled, "employee_id": employee_id}

    def demo_login(self, body):
        if not self.demo_enabled:
            raise HTTPException(404, "Demo sign-in is disabled")
        identity = self.identity("hr" if body.account == "hr" else DEMO_EMPLOYEE_ID)
        if identity is None:
            raise HTTPException(404, "Demo employee is not available")
        with self.store.transaction(write=True) as connection:
            return self._create_session(connection, identity, time.time(), is_demo=True)

    def _create_session(self, connection, identity, now, *, is_demo=False):
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        token = secrets.token_urlsafe(32)
        connection.execute("""INSERT INTO auth_sessions
            (token_hash, username, role, employee_id, expires_at, is_demo) VALUES (?, ?, ?, ?, ?, ?)""", (
            hashlib.sha256(token.encode()).hexdigest(), identity["username"], identity["role"],
            identity["employee_id"], now + SESSION_SECONDS, int(is_demo),
        ))
        return {"access_token": token, "token_type": "bearer", "expires_at": now + SESSION_SECONDS, "user": identity}

    def login(self, body):
        username = canonical_username(body.username)
        identity = self.identity(username)
        expected = hmac.new(self.key, ("career-quest-login:" + username).encode(), hashlib.sha256).hexdigest().upper().encode()
        supplied = body.access_code.strip().upper().encode()
        now = time.time()
        accepted = identity is not None and (
            hmac.compare_digest(expected[:10], supplied) or hmac.compare_digest(expected, supplied)
        )
        with self.store.transaction(write=True) as connection:
            connection.execute("DELETE FROM auth_attempts WHERE until <= ?", (now,))
            attempt = connection.execute("SELECT * FROM auth_attempts WHERE username = ?", (username,)).fetchone()
            if attempt and attempt["failures"] >= 5:
                raise HTTPException(429, "Too many sign-in attempts; try again in one minute", headers={"Retry-After": "60"})
            if not accepted:
                connection.execute("""INSERT INTO auth_attempts VALUES (?, 1, ?)
                    ON CONFLICT(username) DO UPDATE SET failures = failures + 1""", (username, now + 60))
            else:
                connection.execute("DELETE FROM auth_attempts WHERE username = ?", (username,))
                session = self._create_session(connection, identity, now)
        if not accepted:
            raise HTTPException(401, "Invalid account or access code")
        return session

    def session(self, token):
        with self.store.transaction() as connection:
            row = connection.execute("SELECT * FROM auth_sessions WHERE token_hash = ? AND expires_at > ?", (
                hashlib.sha256(token.encode()).hexdigest(), time.time(),
            )).fetchone()
        if row is None or (row["is_demo"] and not self.demo_enabled):
            raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
        return {key: row[key] for key in ("username", "role", "employee_id")}

    def logout(self, token):
        with self.store.transaction(write=True) as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    return request.app.state.auth.session(credentials.credentials)


def hr_user(user=Depends(current_user)):
    if user["role"] != "hr":
        raise HTTPException(403, "HR access required")
    return user


def allow_employee(user, employee_id):
    if user["role"] != "hr" and user["employee_id"] != employee_id:
        raise HTTPException(403, "You can only access your own employee profile")


def main():
    parser = argparse.ArgumentParser(description="Read a local account's private sign-in code. Share only with its owner.")
    parser.add_argument("command", choices=["credentials", "token"])
    parser.add_argument("username", help="hr or employee ID (for example E0002)")
    args = parser.parse_args()
    auth = Auth(Store(database_path()))
    credentials = auth.credentials(args.username)
    if args.command == "token":
        print(auth.login(Login(**credentials))["access_token"])
    else:
        print(json.dumps(credentials))


if __name__ == "__main__":
    main()
