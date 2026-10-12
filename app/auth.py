"""Verifies the JWT monday sends with every integration action call."""

from __future__ import annotations

import logging

import jwt
from fastapi import Header, HTTPException

from .config import get_secret

log = logging.getLogger("kundenname_split")


async def monday_session(authorization: str | None = Header(default=None)) -> dict:
    """
    FastAPI dependency. The token is signed with the app's Signing Secret, so this
    proves the call came from monday. API calls use MONDAY_API_TOKEN, not the
    token's shortLivedToken.
    """
    signing_secret = await get_secret("MONDAY_SIGNING_SECRET")
    if not signing_secret:
        log.error("MONDAY_SIGNING_SECRET is not set")
        raise HTTPException(status_code=500, detail="Server misconfigured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        # monday sets `aud` to the Run URL; we don't pin it so the same build works on any host.
        return jwt.decode(
            token,
            signing_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        log.warning("JWT verification failed: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid token") from exc
