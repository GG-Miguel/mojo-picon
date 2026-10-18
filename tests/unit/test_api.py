import json
from contextlib import asynccontextmanager

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
from mojo_picon.observability import NullTracer, TurnTrace
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


async def make_client(models, store=None, production=False, tracer=None):
    store = store or InMemoryStore()
    await store.save_profile(UserContext(uid="ana"), PROFILE)
    deps = AppDeps(
        verifier=FakeVerifier(),
        store=store,
        foods=FOODS,
        activities=load_met_table(),
        graph=build_graph(models, FOODS),
        tracer=tracer or NullTracer(),
        production=production,
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


async def test_photo_without_vision_model_is_rejected():
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


@pytest.mark.parametrize(
    "change", [{"weekly_rate_kg": 2, "goal": "lose"}, {"weekly_rate_kg": 0.8, "goal": "gain"}, {"timezone": "Foo/Bar"}]
)
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


async def test_day_entries_carry_food_names():
    models = FakeProvider(
        guardian=[OK],
        coach=[tool_call("log_meal", "c1", items=[{"food_id": "gofio", "grams": 30}]), AIMessage("Apuntado.")],
    )
    client, _ = await make_client(models)
    async with client:
        await client.post("/chat", headers=ANA, data={"message": "30 g de gofio"})
        entry = (await client.get("/day", headers=ANA)).json()["entries"][0]
    assert entry["items"][0] == {"food_id": "gofio", "grams": 30.0, "name": "Gofio"}


async def test_frontend_is_served_without_shadowing_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<html>mojo</html>")
    store = InMemoryStore()
    await store.save_profile(UserContext(uid="ana"), PROFILE)
    deps = AppDeps(
        verifier=FakeVerifier(), store=store, foods=FOODS, activities=load_met_table(),
        graph=build_graph(FakeProvider(), FOODS), tracer=NullTracer(), frontend_dir=tmp_path,
    )  # fmt: skip
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(deps)), base_url="http://t") as client:
        assert "mojo" in (await client.get("/")).text
        assert (await client.get("/day")).status_code == 401  # the API still answers, not the SPA


async def test_security_headers_and_no_docs_in_production():
    for production, docs_status in [(False, 200), (True, 404)]:
        client, _ = await make_client(FakeProvider(), production=production)
        async with client:
            response = await client.get("/health")
            assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Content-Security-Policy"] == "frame-ancestors 'self'"
            assert (await client.get("/openapi.json")).status_code == docs_status
            assert (await client.get("/docs")).status_code == docs_status


async def test_no_trace_links_for_users_in_production():
    class Traced(NullTracer):
        @asynccontextmanager
        async def turn(self, user_id, session_id, user_input):
            yield TurnTrace(url="https://cloud.langfuse.com/trace/x")

    for production, expected in [(False, True), (True, False)]:
        models = FakeProvider(guardian=[OK], coach=[AIMessage("Hola.")])
        client, _ = await make_client(models, production=production, tracer=Traced())
        async with client:
            stream = events(await client.post("/chat", headers=ANA, data={"message": "hola"}))
        assert any(e["type"] == "trace" for e in stream) is expected


async def test_sign_in_helpers_are_proxied_from_our_domain_and_nothing_else():
    from mojo_picon.api.auth_proxy import auth_proxy

    seen = []

    def upstream(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200, text="<html>handler</html>", headers={"content-type": "text/html", "set-cookie": "x=1"}
        )

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(
        auth_proxy("mojo-picon.firebaseapp.com", httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        ok = await client.get("/__/auth/handler", params={"apiKey": "k", "authType": "signInViaPopup"})
        assert ok.status_code == 200 and ok.text == "<html>handler</html>"
        assert "set-cookie" not in ok.headers  # only content headers are passed back
        assert seen == ["https://mojo-picon.firebaseapp.com/__/auth/handler?apiKey=k&authType=signInViaPopup"]
        assert (await client.get("/__/auth/..%2F..%2Fadmin")).status_code == 404  # no path escapes
        assert (await client.get("/__/other/handler")).status_code == 404
        assert (await client.post("/__/auth/handler")).status_code == 405  # GET only
    assert len(seen) == 1
