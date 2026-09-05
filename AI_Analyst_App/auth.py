"""
Real per-user authentication: signup, login, password hashing, and signed
session tokens carrying a user id. Each user's data (reports, usage,
subscriptions) is isolated by user_id — see firestore_db.py.

DEV_ACCESS_PASSWORD (config.py) still exists as a separate, optional
shortcut: it logs you in as a special "owner" account that bypasses the
subscription gate, so you (the developer) can exercise the whole app
without going through Paymob. It's unrelated to normal user accounts and
should be left unset once you have real paying users, or restricted to
your own IP via your reverse proxy.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from passlib.context import CryptContext

from config import ADMIN_EMAILS, DEV_ACCESS_PASSWORD, JWT_SECRET, JWT_TTL_MINUTES
from firestore_db import FirestoreDB, get_db
from schemas import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def generate_token_string() -> str:
    """A random URL-safe token for password reset links — unrelated to the
    signed session tokens below (this one is just looked up against the
    matching DB column, not decoded)."""
    return secrets.token_urlsafe(32)


def generate_otp_code() -> str:
    """A 6-digit numeric code for email verification, sent to the user and
    typed back into the UI — friendlier on mobile than a clickable link."""
    return f"{secrets.randbelow(1_000_000):06d}"


def verify_firebase_id_token(id_token: str) -> dict:
    """Verifies a Firebase Auth ID token (issued client-side after Google/Apple/
    email sign-in via the Firebase JS SDK) and returns its decoded claims.
    Raises firebase_admin.auth exceptions on invalid/expired tokens — callers
    should catch and turn those into an HTTP 401.
    """
    from firebase_admin import auth as firebase_auth

    return firebase_auth.verify_id_token(id_token)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(user_id: str) -> str:
    """A minimal signed, expiring token: base64(payload).signature — no external JWT
    dependency needed since we only ever need one claim (user id) plus an expiry."""
    payload = json.dumps({"uid": user_id, "exp": int(time.time()) + JWT_TTL_MINUTES * 60})
    payload_b64 = _b64(payload.encode())
    signature = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def decode_token(token: str) -> Optional[str]:
    """Returns the user id if the token is valid and unexpired, else None."""
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None

    expected = hmac.new(JWT_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        payload = json.loads(_b64_decode(payload_b64))
    except Exception:
        return None

    if payload.get("exp", 0) < time.time():
        return None

    return payload.get("uid")


_OWNER_USER_ID = "dev-owner"


def get_current_user(
    authorization: str = Header(default=""),
    db: FirestoreDB = Depends(get_db),
) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid Authorization header.")

    token = authorization.removeprefix("Bearer ").strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid. Log in again.")

    if user_id == _OWNER_USER_ID:
        # Synthetic owner account for the dev-password shortcut — not a real Firestore doc.
        return User(id=_OWNER_USER_ID, email="owner@local", is_owner=True)

    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")
    return user


def create_owner_token_if_password_matches(password: str) -> Optional[str]:
    """Dev shortcut: DEV_ACCESS_PASSWORD logs in as the owner pseudo-account."""
    if not DEV_ACCESS_PASSWORD:
        return None
    if not hmac.compare_digest(password, DEV_ACCESS_PASSWORD):
        return None
    return create_token(_OWNER_USER_ID)


def is_admin(user: User) -> bool:
    if getattr(user, "is_owner", False):
        return True
    return bool(user.email) and user.email.lower() in ADMIN_EMAILS


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required.")
    return user
