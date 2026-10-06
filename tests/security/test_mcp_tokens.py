"""Attack through MCP over real HTTP: «apunta esto en el diario de otro usuario» must fail.

The server is started on a free local port with two development tokens. Each token can only
read and write its owner's diary; requests without a valid token are rejected.
"""

import asyncio
import socket

import httpx
import pytest
from fastmcp import Client

from mojo_picon.auth import UserContext
from mojo_picon.domain import Profile, Sex
from mojo_picon.mcp_server import DevTokenRegistry, McpTokenVerifier, build_mcp
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods

TOKENS = {"tok-ana": "ana", "tok-yolanda": "yolanda"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def server():
    store = InMemoryStore()
    for uid in TOKENS.values():
        await store.save_profile(UserContext(uid=uid), Profile(age=30, sex=Sex.FEMALE, weight_kg=60, height_cm=165))
    mcp = build_mcp(store, load_foods(), load_met_table(), auth=McpTokenVerifier(DevTokenRegistry(TOKENS, "test")))
    port = free_port()
    task = asyncio.create_task(mcp.run_http_async(host="127.0.0.1", port=port, path="/mcp", show_banner=False))
    url = f"http://127.0.0.1:{port}/mcp"
    for _ in range(50):
        try:
            async with httpx.AsyncClient() as http:
                await http.get(url)
            break
        except httpx.TransportError:
            await asyncio.sleep(0.1)
    yield url, store
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_each_token_only_reaches_its_owners_diary(server):
    url, _ = server
    async with Client(url, auth="tok-yolanda") as yolanda:
        await yolanda.call_tool("log_meal", {"items": [{"food_id": "paella", "grams": 400}]})
    async with Client(url, auth="tok-ana") as ana:
        balance = (await ana.call_tool("get_day_balance", {})).structured_content
    assert balance["meals"] == 0  # Ana cannot see Yolanda's paella


@pytest.mark.parametrize("token", [None, "forged-token"])
async def test_requests_without_a_valid_token_are_rejected(server, token):
    url, _ = server
    async with httpx.AsyncClient() as http:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = await http.post(url, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 401
