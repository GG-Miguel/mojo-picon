"""Personal MCP tokens: one per user, created in the web app, stored only as a hash, revocable.

Milestone 1 uses a development registry configured from the environment; milestone 2 adds the
Firestore registry (`users/{uid}/mcp_tokens/{id}`) behind the same interface.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol

from fastmcp.server.auth import AccessToken, TokenVerifier

from mojo_picon.auth.context import UserContext

MCP_SCOPES = ["diary:read", "diary:write"]  # never delete data or manage tokens (Servidor MCP, Controles)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TokenRegistry(Protocol):
    async def uid_for(self, token_hash: str) -> str | None:
        """The uid that owns a non-revoked token with this hash, or None."""
        ...


class DevTokenRegistry:
    """Development only: tokens from `MCP_DEV_TOKENS="token1:uid1,token2:uid2"`. Refuses production."""

    def __init__(self, tokens: dict[str, str], environment: str):
        if environment == "production":
            raise RuntimeError("DevTokenRegistry must not be used in production")
        self._by_hash = {token_hash(token): uid for token, uid in tokens.items()}

    @property
    def uids(self) -> set[str]:
        return set(self._by_hash.values())

    async def uid_for(self, token_hash: str) -> str | None:
        for known, uid in self._by_hash.items():
            if hmac.compare_digest(known, token_hash):
                return uid
        return None


class McpTokenVerifier(TokenVerifier):
    """FastMCP auth provider: a bearer token -> AccessToken whose subject is the owner's uid."""

    def __init__(self, registry: TokenRegistry):
        super().__init__(required_scopes=MCP_SCOPES)
        self._registry = registry

    async def verify_token(self, token: str) -> AccessToken | None:
        uid = await self._registry.uid_for(token_hash(token))
        if uid is None:
            return None
        return AccessToken(token=token, client_id=f"mcp:{uid}", scopes=MCP_SCOPES, subject=uid)


def user_context_from(access_token: AccessToken | None) -> UserContext:
    if access_token is None or not access_token.subject:
        raise PermissionError("missing or invalid MCP token")
    return UserContext(uid=access_token.subject)
