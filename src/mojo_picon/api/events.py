"""Server-Sent Events contract of POST /chat (API y frontend: Contrato de eventos).

Pydantic models here; the frontend gets TypeScript types from the OpenAPI schema.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StepEvent(BaseModel):
    type: Literal["step"] = "step"
    id: str
    label: str  # Spanish, shown in the step timeline
    status: Literal["start", "done", "failed"]
    detail: str = ""


class AskEvent(BaseModel):
    type: Literal["ask"] = "ask"
    text: str


class FinalEvent(BaseModel):
    type: Literal["final"] = "final"
    text: str
    session_id: str


class DayUpdatedEvent(BaseModel):
    type: Literal["day_updated"] = "day_updated"


class TraceEvent(BaseModel):
    type: Literal["trace"] = "trace"
    url: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


Event = StepEvent | AskEvent | FinalEvent | DayUpdatedEvent | TraceEvent | ErrorEvent


def sse(event: Event) -> str:
    return f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"


TOOL_LABELS = {
    "search_food": "Consultando alimentos",
    "get_nutrients": "Calculando nutrientes",
    "check_allergens": "Comprobando alérgenos",
    "log_meal": "Registrando la comida",
    "list_activities": "Consultando actividades",
    "log_activity": "Registrando la actividad",
    "get_day_balance": "Calculando el balance del día",
    "per_kg_target": "Calculando la cantidad para tu peso",
    "plan_rest_of_day": "Planificando y verificando",
}
DIARY_TOOLS = {"log_meal", "log_activity"}
