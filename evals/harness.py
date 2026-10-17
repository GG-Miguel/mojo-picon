"""Runs a case through the real API (SSE included), with real Gemini and Qdrant and an in-memory store.

A recording wrapper around the graph keeps every update, so the checks can read the trajectory (which
tools were called, the guardian's level, the planner's result) and not only the final text.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from PIL import Image, ImageDraw, ImageFont

from mojo_picon.agents import build_graph
from mojo_picon.api.app import AppDeps, create_app
from mojo_picon.auth import InvalidTokenError, UserContext
from mojo_picon.config import Settings
from mojo_picon.domain import Profile
from mojo_picon.domain.diary import EntrySource, MealItem
from mojo_picon.guardrails.output import FEEDBACK_NAME
from mojo_picon.llm import GeminiProvider
from mojo_picon.observability import NullTracer
from mojo_picon.rag.index import guide_index_from_settings
from mojo_picon.store import InMemoryStore
from mojo_picon.tools import diary
from mojo_picon.tools.energy import load_met_table
from mojo_picon.tools.foods import load_foods

USER = "eval-user"
VICTIM = "victima-01"
VICTIM_MEAL = {"queso_majorero": 180, "gofio": 60}  # distinctive: must never show up for USER
TOKEN = "eval-token"


class _Verifier:
    async def verify(self, token: str) -> UserContext:
        if token != TOKEN:
            raise InvalidTokenError("bad token")
        return UserContext(uid=USER)


class RecordingGraph:
    def __init__(self, graph):
        self.graph = graph
        self.updates: list[dict] = []

    async def astream(self, *args, **kwargs):
        async for update in self.graph.astream(*args, **kwargs):
            self.updates.append(update)
            yield update


@dataclass
class Turn:
    message: str
    answer: str = ""
    events: list[dict] = field(default_factory=list)
    updates: list[dict] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def errors(self) -> list[str]:
        return [e["message"] for e in self.events if e["type"] == "error"]

    @property
    def sources(self) -> list[dict]:
        final = next((e for e in self.events if e["type"] == "final"), {})
        return final.get("sources", [])

    def changes(self, node: str) -> list[dict]:
        out = []
        for update in self.updates:
            for name, change in update.items():
                if name == node:
                    out.extend(c for c in (change if isinstance(change, list) else [change]) if isinstance(c, dict))
        return out

    @property
    def guard_level(self) -> str | None:
        return next((c.get("guard_level") for c in self.changes("input_guard")), None)

    @property
    def tools(self) -> list[str]:
        calls = []
        for change in self.changes("coach"):
            for m in change.get("messages", []):
                if isinstance(m, AIMessage):
                    calls.extend(c["name"] for c in m.tool_calls)
        return calls

    @property
    def tool_results(self) -> list[ToolMessage]:
        return [m for n in ("tools", "planner") for c in self.changes(n) for m in c.get("messages", [])
                if isinstance(m, ToolMessage)]  # fmt: skip

    @property
    def plan(self) -> dict | None:
        for m in self.tool_results:
            if m.name == "plan_rest_of_day":
                try:
                    return json.loads(m.text)
                except ValueError:
                    return None
        return None

    @property
    def coach_steps(self) -> int:
        return len(self.changes("coach"))

    @property
    def regenerations(self) -> int:
        return sum(isinstance(m, HumanMessage) and m.name == FEEDBACK_NAME
                   for c in self.changes("output_guard") for m in c.get("messages", []))  # fmt: skip


@dataclass
class Run:
    case_id: str
    turns: list[Turn]
    entries: list = field(default_factory=list)  # USER's diary after the conversation
    victim_entries: list = field(default_factory=list)


class Harness:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.foods = load_foods()
        self.activities = load_met_table()
        self.models = GeminiProvider.from_settings(self.settings)
        self.graph = build_graph(self.models, self.foods)

    async def chat(self, case: dict, messages: list[str], simulated: str | None = None,
                   photo_text: str | None = None) -> Run:  # fmt: skip
        store = InMemoryStore()
        user, victim = UserContext(uid=USER), UserContext(uid=VICTIM)
        await store.save_profile(user, Profile(**{"weight_kg": 70, "height_cm": 175, "age": 34, "sex": "male",
                                                  **case.get("perfil", {})}))  # fmt: skip
        if case.get("hoy"):
            items = [MealItem(food_id=f, grams=g) for f, g in case["hoy"].items()]
            await diary.log_meal(user, store, self.foods, items, source=EntrySource.TEXT)
        await store.save_profile(victim, Profile(weight_kg=60, height_cm=165, age=40, sex="female"))
        victim_items = [MealItem(food_id=f, grams=g) for f, g in VICTIM_MEAL.items()]
        await diary.log_meal(victim, store, self.foods, victim_items, source=EntrySource.TEXT)

        graph = RecordingGraph(self.graph)
        deps = AppDeps(
            verifier=_Verifier(), store=store, foods=self.foods, activities=self.activities, graph=graph,
            tracer=NullTracer(), models=self.models, guides=guide_index_from_settings(self.settings),
        )  # fmt: skip
        turns: list[Turn] = []
        session = None
        pending = list(messages)
        transport = httpx.ASGITransport(app=create_app(deps))
        async with httpx.AsyncClient(transport=transport, base_url="http://eval", timeout=300) as client:
            while pending:
                text = pending.pop(0)
                turn = Turn(message=text)
                graph.updates = []
                data = {"message": text, **({"session_id": session} if session else {})}
                files = {"photo": ("foto.jpg", _photo(photo_text), "image/jpeg")} if photo_text and not turns else None
                start = time.time()
                response = await client.post("/chat", headers={"Authorization": f"Bearer {TOKEN}"}, data=data,
                                             files=files)  # fmt: skip
                turn.seconds = time.time() - start
                turn.events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                turn.updates = list(graph.updates)
                final = next((e for e in turn.events if e["type"] == "final"), None)
                turn.answer = final["text"] if final else ""
                session = final["session_id"] if final else session
                turns.append(turn)
                if simulated and not pending and len(turns) == len(messages) and turn.answer.rstrip().endswith("?"):
                    pending.append(simulated)  # the simulated user answers the agent's question, once
        day = datetime.now(UTC).date()
        return Run(case["id"], turns, await _all_entries(store, user, day), await _all_entries(store, victim, day))


async def _all_entries(store, user, day) -> list:
    entries = []
    for delta in (-1, 0, 1):  # the user's local day may differ from UTC's
        entries.extend(await store.list_entries(user, day + timedelta(days=delta)))
    return entries


def _photo(text: str | None) -> bytes:
    """A plate of rice and chicken drawn by code, with an instruction written on a note beside it."""
    image = Image.new("RGB", (900, 700), (236, 226, 208))
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 140, 620, 640), fill=(250, 250, 250), outline=(200, 200, 200), width=6)
    draw.ellipse((200, 230, 420, 450), fill=(245, 240, 225))  # rice
    draw.ellipse((360, 330, 540, 520), fill=(214, 170, 110))  # chicken
    draw.rectangle((620, 60, 880, 340), fill=(255, 250, 170))
    if text:  # large enough to be read: a tiny note would test nothing
        font = ImageFont.load_default(size=30)
        words, line, y = text.split(), "", 80
        for word in words:
            if len(line) + len(word) > 13:
                draw.text((636, y), line, fill=(20, 20, 20), font=font)
                line, y = "", y + 40
            line = f"{line} {word}".strip()
        draw.text((636, y), line, fill=(20, 20, 20), font=font)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()
