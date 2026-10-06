import json

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mojo_picon.auth import UserContext
from mojo_picon.domain import Allergen, Profile, Sex
from mojo_picon.mcp_server import build_mcp
from mojo_picon.mcp_server.tokens import DevTokenRegistry, McpTokenVerifier, token_hash, user_context_from
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods

ANA = UserContext(uid="ana")
PROFILE = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175, allergens=frozenset({Allergen.TREE_NUTS}))


@pytest.fixture
async def store():
    s = InMemoryStore()
    await s.save_profile(ANA, PROFILE)
    return s


@pytest.fixture
def mcp(store):
    return build_mcp(store, load_foods(), load_met_table(), auth=None, resolve_context=lambda: ANA)


async def call(mcp, tool, **arguments):
    async with Client(mcp) as client:
        result = await client.call_tool(tool, arguments)
        return result.structured_content


async def test_only_deterministic_tools_are_exposed(mcp):
    # ADR-21: nothing that reasons (no plan_rest_of_day) goes through MCP
    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {
        "search_food",
        "get_nutrients",
        "check_allergens",
        "list_activities",
        "log_meal",
        "log_activity",
        "get_day_balance",
    }


async def test_tools_have_no_user_parameter(mcp):
    async with Client(mcp) as client:
        for tool in await client.list_tools():
            assert not {"uid", "user_id", "user"} & set(tool.input_schema.get("properties", {})), tool.name


async def test_demo_flow_paella_then_remaining_protein(mcp, store):
    # UC-09: «apunta que he comido paella y dime cuánta proteína me queda»
    found = await call(mcp, "search_food", query="paella")
    assert found["status"] == "exact"
    food_id = found["candidates"][0]["food_id"]

    entry = await call(mcp, "log_meal", items=[{"food_id": food_id, "grams": 350}], request_id="r1")
    assert entry["source"] == "mcp"

    balance = await call(mcp, "get_day_balance")
    assert balance["meals"] == 1
    assert balance["remaining"]["protein_g"] < balance["target"]["target"]["protein_g"]


async def test_log_meal_is_idempotent_by_request_id(mcp, store):
    for _ in range(2):
        await call(mcp, "log_meal", items=[{"food_id": "platano", "grams": 120}], request_id="same")
    assert (await call(mcp, "get_day_balance"))["meals"] == 1


async def test_check_allergens_uses_the_profile(mcp):
    assert await call(mcp, "check_allergens", food_ids=["almendras", "tomate"]) == {"almendras": ["tree_nuts"]}


async def test_log_activity_by_distance(mcp):
    entry = await call(mcp, "log_activity", activity_id="running_9.7kmh", distance_km=10)
    assert entry["kcal"] > 500


async def test_errors_are_explicit_and_nothing_is_invented(mcp):
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="meal not logged"):
            await client.call_tool("log_meal", {"items": [{"food_id": "dragon_fruit", "grams": 100}]})
        with pytest.raises(ToolError, match="unknown activity"):
            await client.call_tool("log_activity", {"activity_id": "quidditch", "minutes": 30})


async def test_resources(mcp):
    async with Client(mcp) as client:
        profile = json.loads((await client.read_resource("profile://me"))[0].text)
        assert profile["weight_kg"] == 70
        assert json.loads((await client.read_resource("diary://today"))[0].text) == []


# --- tokens -------------------------------------------------------------------------


async def test_dev_registry_maps_token_hashes_to_uids():
    registry = DevTokenRegistry({"tok-a": "ana", "tok-y": "yolanda"}, environment="development")
    assert await registry.uid_for(token_hash("tok-a")) == "ana"
    assert await registry.uid_for(token_hash("tok-unknown")) is None


def test_dev_registry_refuses_production():
    with pytest.raises(RuntimeError):
        DevTokenRegistry({"tok-a": "ana"}, environment="production")


async def test_verifier_puts_the_owner_in_the_subject():
    verifier = McpTokenVerifier(DevTokenRegistry({"tok-a": "ana"}, "development"))
    access = await verifier.verify_token("tok-a")
    assert user_context_from(access) == ANA
    assert await verifier.verify_token("forged") is None


def test_missing_token_is_rejected():
    with pytest.raises(PermissionError):
        user_context_from(None)


# --- review findings (2026-10-12) ---------------------------------------------------


@pytest.mark.parametrize("request_id", ["x/y/z", "../a", "a" * 65])
async def test_unsafe_request_ids_are_rejected(mcp, request_id):
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "log_meal", {"items": [{"food_id": "platano", "grams": 100}], "request_id": request_id}
            )


async def test_diary_uses_the_profile_timezone(store):
    mexico = PROFILE.model_copy(update={"timezone": "America/Mexico_City"})
    await store.save_profile(ANA, mexico)
    server = build_mcp(store, load_foods(), load_met_table(), auth=None, resolve_context=lambda: ANA)
    entry = await call(server, "log_meal", items=[{"food_id": "platano", "grams": 100}])
    from datetime import datetime
    from zoneinfo import ZoneInfo

    local_day = datetime.fromisoformat(entry["timestamp"]).astimezone(ZoneInfo("America/Mexico_City")).date()
    assert len(await store.list_entries(ANA, local_day)) == 1
