import json

import httpx
import pytest
from langchain_core.messages import AIMessage
from tests.fakes import FakeProvider, tool_call

from mojo_picon.agents import build_graph
from mojo_picon.api.app import RATE_LIMIT_PER_MINUTE, AppDeps, create_app
from mojo_picon.auth import InvalidTokenError, UserContext
from mojo_picon.domain import Profile, Sex
from mojo_picon.guardrails.responses import fixed_response
from mojo_picon.guardrails.rules import GuardDecision
from mojo_picon.llm import Role
from mojo_picon.observability import NullTracer
from mojo_picon.store import InMemoryStore
from mojo_picon.tools.energy import daily_target, load_met_table
from mojo_picon.tools.foods import load_foods

FOODS = load_foods()
PROFILE = Profile(age=34, sex=Sex.MALE, weight_kg=70, height_cm=175)
OK = GuardDecision(level="ok", category="none")
TOKENS = {"tok-ana": "ana", "tok-yolanda": "yolanda"}


class FakeVerifier:
    async def verify(self, token: str) -> UserContext:
        if token not in TOKENS:
            raise InvalidTokenError("bad token")
        return UserContext(uid=TOKENS[token])


async def make_client(models, store=None):
    store = store or InMemoryStore()
    await store.save_profile(UserContext(uid="ana"), PROFILE)
    deps = AppDeps(
        verifier=FakeVerifier(),
        store=store,
        foods=FOODS,
        activities=load_met_table(),
        graph=build_graph(models, FOODS),
        tracer=NullTracer(),
    )
    transport = httpx.ASGITransport(app=create_app(deps))
    return httpx.AsyncClient(transport=transport, base_url="http://test"), store


def events(response) -> list[dict]:
    found = []
    for block in response.text.strip().split("\n\n"):
        data = next(line[6:] for line in block.splitlines() if line.startswith("data: "))
        found.append(json.loads(data))
    return found


ANA = {"Authorization": "Bearer tok-ana"}


async def test_requests_without_a_valid_token_are_rejected():
    client, _ = await make_client(FakeProvider())
    async with client:
        assert (await client.get("/day")).status_code == 401
        assert (await client.get("/day", headers={"Authorization": "Bearer forged"})).status_code == 401
        assert (await client.get("/health")).status_code == 200


async def test_chat_streams_steps_final_answer_and_day_update():
    expected = round(daily_target(PROFILE).target.kcal - round(FOODS["platano"].nutrients_for(120).kcal, 1))
    models = FakeProvider(
        guardian=[OK],
        coach=[
            tool_call("log_meal", "c1", items=[{"food_id": "platano", "grams": 120}]),
            tool_call("get_day_balance", "c2"),
            AIMessage(f"Apuntado. Te quedan {expected} kcal."),
        ],
    )
    client, _ = await make_client(models)
    async with client:
        response = await client.post("/chat", headers=ANA, data={"message": "Me he comido un plátano de 120 g"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = events(response)
    types = [e["type"] for e in stream]
    assert types[0] == "step" and stream[0]["label"] == "Comprobación de seguridad"
    assert {"id": "c1", "status": "start"}.items() <= next(e for e in stream if e.get("id") == "c1").items()
    final = next(e for e in stream if e["type"] == "final")
    assert final["text"] == f"Apuntado. Te quedan {expected} kcal."
    assert types[-1] == "day_updated"


async def test_derivation_is_streamed_without_calling_the_coach():
    models = FakeProvider()
    client, _ = await make_client(models)
    async with client:
        response = await client.post("/chat", headers=ANA, data={"message": "¿Cuánta insulina me pongo?"})
    final = next(e for e in events(response) if e["type"] == "final")
    assert final["text"] == fixed_response("medication")
    assert models.get(Role.COACH).calls == 0


async def test_the_session_keeps_recent_messages_between_turns():
    models = FakeProvider(guardian=[OK, OK], coach=[AIMessage("¿Qué pan era?"), AIMessage("Vale, pan integral.")])
    client, store = await make_client(models)
    async with client:
        first = await client.post("/chat", headers=ANA, data={"message": "He comido pan"})
        session_id = next(e for e in events(first) if e["type"] == "final")["session_id"]
        await client.post("/chat", headers=ANA, data={"message": "Integral", "session_id": session_id})
    second_prompt = models.get(Role.COACH).received[1]
    assert [m.text for m in second_prompt[1:]] == ["He comido pan", "¿Qué pan era?", "Integral"]
    session = await store.get_session(UserContext(uid="ana"), session_id)
    assert len(session.messages) == 4


async def test_sessions_of_other_users_are_not_reachable():
    models = FakeProvider(guardian=[OK, OK], coach=[AIMessage("Hola Ana."), AIMessage("Hola.")])
    client, store = await make_client(models)
    await store.save_profile(UserContext(uid="yolanda"), PROFILE)
    async with client:
        first = await client.post("/chat", headers=ANA, data={"message": "Soy Ana"})
        session_id = next(e for e in events(first) if e["type"] == "final")["session_id"]
        await client.post(
            "/chat", headers={"Authorization": "Bearer tok-yolanda"}, data={"message": "Hola", "session_id": session_id}
        )
    # Yolanda used Ana's session id but got a fresh, empty session of her own
    yolanda_prompt = models.get(Role.COACH).received[1]
    assert [m.text for m in yolanda_prompt[1:]] == ["Hola"]


async def test_day_and_profile_endpoints():
    client, _ = await make_client(FakeProvider())
    async with client:
        day = (await client.get("/day", headers=ANA)).json()
        assert day["balance"]["target"]["target"]["kcal"] == daily_target(PROFILE).target.kcal
        assert day["entries"] == []
        yolanda = {"Authorization": "Bearer tok-yolanda"}
        assert (await client.get("/me/profile", headers=yolanda)).status_code == 404
        put = await client.put("/me/profile", headers=yolanda, json=PROFILE.model_dump(mode="json"))
        assert put.status_code == 200
        assert (await client.get("/me/profile", headers=yolanda)).json()["weight_kg"] == 70


@pytest.mark.parametrize("session_id", ["../yolanda", "a/b", "x" * 65])
async def test_unsafe_session_ids_are_rejected(session_id):
    client, _ = await make_client(FakeProvider())
    async with client:
        response = await client.post("/chat", headers=ANA, data={"message": "hola", "session_id": session_id})
    assert response.status_code == 422


async def test_photo_is_not_available_yet():
    client, _ = await make_client(FakeProvider())
    async with client:
        response = await client.post(
            "/chat", headers=ANA, data={"message": "esto"}, files={"photo": ("p.jpg", b"\xff\xd8", "image/jpeg")}
        )
    assert response.status_code == 501


async def test_rate_limit():
    client, _ = await make_client(FakeProvider())
    async with client:
        codes = [(await client.get("/day", headers=ANA)).status_code for _ in range(RATE_LIMIT_PER_MINUTE + 1)]
    assert codes[-1] == 429 and codes[0] == 200


# --- review findings (2026-10-12) ---------------------------------------------------


@pytest.mark.parametrize("change", [{"weekly_rate_kg": 2, "goal": "lose"}, {"timezone": "Foo/Bar"}])
async def test_profiles_that_would_break_the_account_are_rejected(change):
    client, _ = await make_client(FakeProvider())
    async with client:
        body = PROFILE.model_dump(mode="json") | change
        assert (await client.put("/me/profile", headers=ANA, json=body)).status_code == 422


async def test_derived_turns_are_not_kept_in_the_session():
    models = FakeProvider(guardian=[OK], coach=[AIMessage("¿Qué entreno has hecho?")])
    client, _store = await make_client(models)
    async with client:
        first = await client.post("/chat", headers=ANA, data={"message": "¿Cuánta insulina me pongo?"})
        session_id = next(e for e in events(first) if e["type"] == "final")["session_id"]
        await client.post("/chat", headers=ANA, data={"message": "¿Y antes de correr?", "session_id": session_id})
    prompt = models.get(Role.COACH).received[0]
    assert all("insulina" not in m.text for m in prompt[1:])
