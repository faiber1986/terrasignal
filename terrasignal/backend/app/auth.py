"""Demo authentication: locally-signed JWT, three seeded users, server-side RBAC.

Production path: Cognito JWT with the same role claims — only `decode_token`
changes. Frontend role-hiding is UX; these dependencies are the security.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from terrasignal.settings import get_settings

ALGO = "HS256"

DEMO_USERS = {
    "ana.analyst": {"password": "demo", "role": "analyst", "name": "Ana Torres"},
    "alex.approver": {"password": "demo", "role": "approver", "name": "Alex Romero"},
    "admin": {"password": "demo", "role": "admin", "name": "Platform Admin"},
}

ROLE_RANK = {"analyst": 1, "approver": 2, "admin": 3}


class User(BaseModel):
    username: str
    role: str
    name: str


def issue_token(username: str, password: str) -> str:
    user = DEMO_USERS.get(username)
    if user is None or user["password"] != password:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    payload = {
        "sub": username,
        "role": user["role"],
        "name": user["name"],
        "exp": datetime.now(UTC) + timedelta(hours=12),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGO)


_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=[ALGO])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from e
    return User(username=payload["sub"], role=payload["role"], name=payload["name"])


def require_role(minimum: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"requires role >= {minimum}; you are {user.role}",
            )
        return user

    return dependency
