"""Password authentication and revocable opaque sessions. No browser-stored tokens."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import LoginCredential, LoginSession, User
from app.domain.enums import UserStatus

COOKIE = "urjasetu_session"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${key.hex()}"


def check_password(password: str, encoded: str) -> bool:
    try:
        _, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def resolve(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    login = session.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == token_hash(token),
            LoginSession.expires_at > datetime.now(UTC),
        )
    )
    user = session.get(User, login.user_id) if login else None
    return user if user and user.status == UserStatus.ACTIVE else None


def require_user(session: Session, request: Request) -> User:
    user = resolve(session, request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user


def create_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        LoginSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(hours=12),
        )
    )
    return token


def authenticate(session: Session, email: str, password: str) -> User:
    credential = session.scalar(
        select(LoginCredential).where(LoginCredential.email == email.lower().strip())
    )
    # Perform the same expensive hash when the email does not exist.
    encoded = credential.password_hash if credential else "scrypt$" + "00" * 16 + "$" + "00" * 64
    if not check_password(password, encoded) or not credential:
        raise HTTPException(401, "Email or password is incorrect.")
    user = session.get(User, credential.user_id)
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(403, "Account is inactive.")
    return user
