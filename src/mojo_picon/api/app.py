"""FastAPI app: the agent as a service; the web is one client among others (ADR-06).

Every route takes the user from the verified Firebase token (ADR-14). POST /chat streams the
agent's steps as Server-Sent Events while the turn runs.

No `from __future__ import annotations` here: FastAPI resolves the route annotations at runtime,
including the `User` dependency alias defined inside create_app.
"""

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from mojo_picon.agents import AgentContext
from mojo_picon.api.auth_proxy import auth_proxy
from mojo_picon.api.events import (
    DIARY_TOOLS,
    TOOL_LABELS,
    DayUpdatedEvent,
    ErrorEvent,
    FinalEvent,
    SourceRef,
    StepEvent,
    TraceEvent,
    sse,
)
from mojo_picon.auth import InvalidTokenError, TokenVerifier, UserContext, bearer_token
from mojo_picon.domain import Food, Profile
from mojo_picon.domain.diary import Session, SessionMessage
from mojo_picon.guardrails.number_origin import citations
from mojo_picon.guardrails.output import FEEDBACK_NAME, RETRIEVAL_TOOL
from mojo_picon.llm import ModelProvider
from mojo_picon.observability import Tracer
from mojo_picon.rag.index import GuideSearch
from mojo_picon.store.base import Store
from mojo_picon.tools import diary
from mojo_picon.tools.energy import MetActivity
from mojo_picon.tools.food_search import FoodIndex
from mojo_picon.vision.extractor import MAX_BYTES, InvalidImageError, extract, prepare_image, summarise

log = logging.getLogger(__name__)
SESSION_MESSAGES = 10  # recent messages kept between turns (summary of older ones: milestone 2)
MAX_MESSAGE_CHARS = 2000
RATE_LIMIT_PER_MINUTE = 30


@dataclass
class AppDeps:
    verifier: TokenVerifier
    store: Store
    foods: Mapping[str, Food]
    activities: Mapping[str, MetActivity]
    graph: Any  # compiled LangGraph
    tracer: Tracer
    expert_brief: str = ""
    brief_passages: Mapping[str, str] | None = None
    frontend_dir: Path | None = None  # compiled React app (frontend/dist), if served here
    models: ModelProvider | None = None  # for the vision extractor (photos); None: photos rejected
    guides: GuideSearch | None = None  # guideline index (RAG); None: expert brief only
    production: bool = False  # no API docs and no trace links for users (security review 2026-10-16)
    auth_proxy_host: str | None = None  # <project>.firebaseapp.com: sign-in served from our domain (Safari)


class RateLimiter:
    """Requests per user per minute, in memory (one per instance; shared limit in milestone 2)."""

    def __init__(self, per_minute: int):
        self._per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self._per_minute:
            raise HTTPException(status_code=429, detail="too many requests")
        hits.append(now)


def create_app(deps: AppDeps) -> FastAPI:
    docs = {} if not deps.production else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Mojo Picón API", version="0.1.0", **docs)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        # A full Content-Security-Policy (with the Firebase login domains) comes in milestone 2
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Same origin only: Firebase's sign-in iframe (/__/auth/iframe) is embedded by our own page
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        return response

    limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)
    index = FoodIndex(deps.foods)

    async def current_user(authorization: Annotated[str | None, Header()] = None) -> UserContext:
        try:
            user = await deps.verifier.verify(bearer_token(authorization))
        except InvalidTokenError as e:
            raise HTTPException(status_code=401, detail="invalid or missing token") from e
        limiter.check(user.uid)
        profile = await deps.store.get_profile(user)
        if profile and profile.timezone != user.timezone:
            user = UserContext(uid=user.uid, roles=user.roles, timezone=profile.timezone)
        return user

    User = Annotated[UserContext, Depends(current_user)]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/me/profile")
    async def get_profile(user: User) -> Profile:
        profile = await deps.store.get_profile(user)
        if profile is None:
            raise HTTPException(status_code=404, detail="no profile yet")
        return profile

    @app.put("/me/profile")
    async def put_profile(user: User, profile: Profile) -> Profile:
        return await diary.update_profile(user, deps.store, profile)

    @app.get("/day")
    async def get_day(user: User) -> dict:
        try:
            balance = await diary.get_day_balance(user, deps.store)
        except diary.ProfileMissingError as e:
            raise HTTPException(status_code=404, detail="no profile yet") from e
        entries = await deps.store.list_entries(user, balance.day)
        return {"balance": balance, "entries": [_with_names(e, deps) for e in entries]}

    @app.post("/chat")
    async def chat(
        user: User,
        message: Annotated[str, Form(max_length=MAX_MESSAGE_CHARS)],
        session_id: Annotated[str | None, Form(pattern=r"^[A-Za-z0-9_-]{1,64}$")] = None,
        photo: UploadFile | None = None,
    ) -> StreamingResponse:
        jpeg = None
        if photo is not None:
            if deps.models is None:
                raise HTTPException(status_code=501, detail="photo analysis is not available")
            try:
                # Cleaned in memory (EXIF and GPS removed) and never stored (Análisis de fotos)
                jpeg = prepare_image(await photo.read(MAX_BYTES + 1))
            except InvalidImageError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        session_id = session_id or uuid.uuid4().hex
        profile = await deps.store.get_profile(user)
        context = AgentContext(
            user=user,
            store=deps.store,
            foods=deps.foods,
            food_index=index,
            activities=deps.activities,
            profile=profile,
            expert_brief=deps.expert_brief,
            brief_passages=deps.brief_passages or {},
            guides=deps.guides,
        )
        return StreamingResponse(
            _run_turn(deps, context, session_id, message, jpeg),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if deps.auth_proxy_host:
        app.include_router(auth_proxy(deps.auth_proxy_host))

    if deps.frontend_dir is not None:
        # The compiled React app, served by the same container (registered last: API routes win)
        app.mount("/", StaticFiles(directory=deps.frontend_dir, html=True), name="frontend")
    return app


def _with_names(entry, deps: AppDeps) -> dict:
    """Diary entry for the web, with food and activity names next to their ids."""
    data = entry.model_dump(mode="json")
    if data["kind"] == "meal":
        for item in data["items"]:
            food = deps.foods.get(item["food_id"])
            item["name"] = food.name if food else item["food_id"]
    else:
        activity = deps.activities.get(data["activity_id"])
        data["name"] = activity.name if activity else data["activity_id"]
    return data


async def _run_turn(
    deps: AppDeps, context: AgentContext, session_id: str, text: str, jpeg: bytes | None = None
) -> AsyncIterator[str]:
    user = context.user
    if jpeg is not None:
        # The vision extractor runs before the graph; only its structured result goes on, as data.
        yield sse(StepEvent(id="vision", label="Analizando la foto", status="start"))
        try:
            summary = summarise(await extract(deps.models, jpeg), context.food_index)
        except Exception:
            log.exception("vision failed")
            yield sse(StepEvent(id="vision", label="Analizando la foto", status="failed"))
            yield sse(ErrorEvent(message="No he podido analizar la foto. Descríbeme qué has comido."))
        else:
            yield sse(StepEvent(id="vision", label="Analizando la foto", status="done", detail=summary.label))
            text = f"{text}\n\n{summary.text}"
        jpeg = None  # drop the image as soon as it has been analysed
    session = await deps.store.get_session(user, session_id) or Session(id=session_id, updated_at=datetime.now(UTC))
    history: list[BaseMessage] = [
        HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in session.messages
    ]
    final_text = ""
    retrieved: dict[str, tuple[str, str]] = {}  # passage tag -> (document title, url)
    diary_changed = False
    derived = False
    try:
        async with deps.tracer.turn(user.uid, session_id, text) as trace:
            config = {"callbacks": trace.callbacks}
            graph_input = {"messages": [*history, HumanMessage(text)]}
            async for update in deps.graph.astream(graph_input, context=context, config=config, stream_mode="updates"):
                for node, change in _node_changes(update):
                    if node == "input_guard" and change.get("guard_level") == "derivar":
                        derived = True
                    for event in _events_for(node, change):
                        yield sse(event)
                    for m in change.get("messages", []):
                        if isinstance(m, AIMessage) and not m.tool_calls:
                            final_text = m.text
                        if isinstance(m, ToolMessage) and m.name in DIARY_TOOLS and m.status != "error":
                            diary_changed = True
                        if isinstance(m, ToolMessage) and m.name == RETRIEVAL_TOOL and m.status != "error":
                            retrieved.update(_passage_documents(m.text))
            if trace.url and not deps.production:  # trace links are for the developer, not for users
                yield sse(TraceEvent(url=trace.url))
    except Exception:
        log.exception("turn failed")
        yield sse(ErrorEvent(message="No he podido completar la respuesta. Inténtalo de nuevo."))
        return

    yield sse(FinalEvent(text=final_text, session_id=session_id, sources=_cited_sources(final_text, retrieved)))
    if diary_changed:
        yield sse(DayUpdatedEvent())
    if derived:
        # A risky question stays out of the history: the next turn's Coach must not answer it
        # indirectly («¿y antes de correr?» after an insulin question).
        return
    messages = [*session.messages, SessionMessage(role="user", content=text)]
    if final_text:
        messages.append(SessionMessage(role="assistant", content=final_text))
    await deps.store.save_session(
        user, Session(id=session_id, messages=messages[-SESSION_MESSAGES:], updated_at=datetime.now(UTC))
    )


def _node_changes(update: dict) -> list[tuple[str, dict]]:
    """(node, change) pairs of a streamed update. A node's change is usually a dict, but the tool
    node gives a list when several tools return a Command in the same step (parallel searches)."""
    pairs: list[tuple[str, dict]] = []
    for node, change in update.items():
        for item in change if isinstance(change, list) else [change]:
            if isinstance(item, dict):
                pairs.append((node, item))
    return pairs


def _passage_documents(tool_result: str) -> dict[str, tuple[str, str]]:
    try:
        passages = json.loads(tool_result).get("pasajes", [])
    except (ValueError, AttributeError):
        return {}
    return {p["etiqueta"]: (p.get("documento", ""), p.get("url", "")) for p in passages if "etiqueta" in p}


def _cited_sources(answer: str, retrieved: dict[str, tuple[str, str]]) -> list[SourceRef]:
    """Documents of the retrieved passages that the answer actually cites ("[EFSA DRV 2017]" cites
    every passage of that document; tags are compared like the output guardian does)."""
    cited = citations(answer)
    documents: dict[tuple[str, str], list[str]] = {}
    for tag, document in retrieved.items():
        norm = " ".join(tag.split()).lower()
        if any(norm == c or any(norm.startswith(c + sep) for sep in (",", " ", ".")) for c in cited):
            documents.setdefault(document, []).append(tag)
    return [SourceRef(title=title, url=url, tags=tags) for (title, url), tags in documents.items()]


def _events_for(node: str, change: dict) -> list[StepEvent]:
    events: list[StepEvent] = []
    if node == "input_guard":
        level = change.get("guard_level", "ok")
        detail = {"ok": "sin señales de alarma", "aviso": "respuesta con aviso", "derivar": "derivación"}[level]
        events.append(StepEvent(id="input_guard", label="Comprobación de seguridad", status="done", detail=detail))
    for m in change.get("messages", []):
        if isinstance(m, AIMessage) and m.tool_calls:
            for call in m.tool_calls:
                label = TOOL_LABELS.get(call["name"], call["name"])
                events.append(StepEvent(id=call["id"], label=label, status="start"))
        elif isinstance(m, ToolMessage):
            status = "failed" if m.status == "error" else "done"
            events.append(StepEvent(id=m.tool_call_id, label=TOOL_LABELS.get(m.name, m.name or ""), status=status))
        elif isinstance(m, HumanMessage) and m.name == FEEDBACK_NAME:
            events.append(
                StepEvent(id=f"verify-{m.id}", label="Verificando cifras", status="failed", detail="corrigiendo")
            )
    return events
