"""Run the MCP server locally (milestone 1): http://localhost:8000/mcp

    MCP_DEV_TOKENS="dev-token-ana:ana" STORE=memory uv run python -m mojo_picon.mcp_server

MCP_DEV_TOKENS: development tokens, "token:uid,…" (refused when ENVIRONMENT=production).
STORE=memory creates a demo profile per development user; STORE=firestore uses the real database.
In milestone 2 the server is mounted in the FastAPI app at /mcp, with per-user tokens in Firestore.
"""

from __future__ import annotations

import os

from mojo_picon.config import Settings
from mojo_picon.devtools import dev_store, require_development
from mojo_picon.mcp_server.server import build_mcp
from mojo_picon.mcp_server.tokens import DevTokenRegistry, McpTokenVerifier
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods


def main() -> None:
    settings = Settings.from_env()
    require_development(settings, "The local MCP server")
    registry = DevTokenRegistry(settings.mcp_dev_tokens, settings.environment)
    store = dev_store(settings, registry.uids)
    mcp = build_mcp(store, load_foods(), load_met_table(), auth=McpTokenVerifier(registry))
    mcp.run(transport="http", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), path="/mcp")


if __name__ == "__main__":
    main()
