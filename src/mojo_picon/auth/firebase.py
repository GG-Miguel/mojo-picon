"""Firebase Authentication: verify an ID token and build the UserContext.

The uid always comes from the verified token, never from the request body or the model
(Principles #4, ADR-14).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol

from mojo_picon.auth.context import UserContext


class InvalidTokenError(Exception):
    """The token is missing, expired, revoked or not issued for this project."""


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> UserContext: ...

    async def delete_account(self, uid: str) -> None:
        """Delete the sign-in account itself (right to erasure); its tokens stop working."""
        ...


class FirebaseTokenVerifier:
    """Verifies Firebase ID tokens with the Admin SDK (Application Default Credentials on Cloud Run)."""

    def __init__(self, project_id: str, check_revoked: bool = True):
        import firebase_admin

        try:
            self._app = firebase_admin.get_app()
        except ValueError:
            self._app = firebase_admin.initialize_app(options={"projectId": project_id})
        self._check_revoked = check_revoked

    async def verify(self, token: str) -> UserContext:
        from firebase_admin import auth

        if not token:
            raise InvalidTokenError("missing token")
        try:
            # The Admin SDK is synchronous (it may fetch Google's public keys): run it in a thread.
            claims = await asyncio.to_thread(
                auth.verify_id_token, token, app=self._app, check_revoked=self._check_revoked
            )
        except (ValueError, auth.InvalidIdTokenError, auth.UserDisabledError, auth.CertificateFetchError) as e:
            # Expired and revoked tokens are InvalidIdTokenError subclasses; a disabled account or a
            # failure to fetch Google's keys also means "not authenticated" (401), not a server error.
            raise InvalidTokenError(str(e)) from e
        # Email and password accounts must verify their email first (anyone can type someone else's
        # address); Google accounts come verified. The frontend asks for it too, this is the server's check.
        provider = (claims.get("firebase") or {}).get("sign_in_provider")
        if provider == "password" and claims.get("email_verified") is not True:
            raise InvalidTokenError("email not verified")
        roles = frozenset({"user", "admin"} if claims.get("admin") is True else {"user"})
        return UserContext(uid=claims["uid"], roles=roles)


def bearer_token(authorization_header: str | None) -> str:
    """Extract the token from an `Authorization: Bearer <token>` header."""
    if not authorization_header:
        raise InvalidTokenError("missing Authorization header")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise InvalidTokenError("expected a Bearer token")
    return token.strip()

    async def delete_account(self, uid: str) -> None:
        from firebase_admin import auth

        with contextlib.suppress(auth.UserNotFoundError):  # already deleted: erasure is idempotent
            await asyncio.to_thread(auth.delete_user, uid, app=self._app)
