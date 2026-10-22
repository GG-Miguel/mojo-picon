"""The judge for G-Eval: GPT-OSS 120B, another model family than the agents (ADR-13).

Served by Vertex AI (default since 22 Oct: billed with the project, no daily cap that matters) or by Groq
(JUDGE=groq; its free tier allows 200k tokens a day, about 16 judged conversations). Same model on both,
so the calibration against the author holds; evals.calibrate checks it again when the provider changes.
It only sees synthetic test cases, never user data, so a provider outside the EU is acceptable here
(Vertex serves it on the global endpoint only). On a rate limit (HTTP 429) it waits and retries the SAME
model: switching judges in the middle of a run would make the scores of different variants incomparable.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time

import httpx
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-oss-120b"
VERTEX_URL = (
    "https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/endpoints/openapi/chat/completions"
)
VERTEX_JUDGE_MODEL = "openai/gpt-oss-120b-maas"
# Fail fast rather than hang: on 22 Oct, with Vertex slow, 120 s per call and 8 attempts let one
# control run go past an hour without a word. A call now gives up after about 3 minutes in the worst
# case; JUDGE_TIMEOUT and JUDGE_ATTEMPTS widen it for a patient run (e.g. Groq's rate limits).
TIMEOUT = float(os.environ.get("JUDGE_TIMEOUT", "45"))
MAX_ATTEMPTS = int(os.environ.get("JUDGE_ATTEMPTS", "4"))
MAX_WAIT = 20  # seconds between attempts, at most
USER_AGENT = "mojo-picon-eval/0.1"  # Groq and other gateways reject generic HTTP-library agents


def make_judge() -> DeepEvalBaseLLM:
    """The judge chosen by JUDGE (vertex, the default, or groq)."""
    provider = os.environ.get("JUDGE", "vertex")
    if provider == "groq":
        return GroqJudge()
    if provider == "vertex":
        return VertexJudge()
    raise ValueError(f"unknown JUDGE {provider!r}: vertex or groq")


class GroqJudge(DeepEvalBaseLLM):
    provider = "Groq"

    def __init__(self, model: str = JUDGE_MODEL, api_key: str | None = None):
        self.model_name = model
        self._key = api_key or os.environ["GROQ_API_KEY"]
        self._url = GROQ_URL
        self.calls = 0
        self.tokens = 0

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"{self.model_name} ({self.provider})"

    def _token(self) -> str:
        return self._key

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        return asyncio.run(self.a_generate(prompt, schema))

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        body = {"model": self.model_name, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}
        if schema is not None:
            body["response_format"] = {"type": "json_object"}
            body["messages"][0]["content"] += "\n\nResponde solo con un objeto JSON válido."
        text = await self._post(body)
        if schema is None:
            return text
        return schema.model_validate_json(_json_block(text))

    async def _post(self, body: dict) -> str:
        headers = {"authorization": f"Bearer {self._token()}", "user-agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for attempt in range(MAX_ATTEMPTS):
                try:
                    response = await client.post(self._url, json=body, headers=headers)
                except httpx.TimeoutException:  # a slow moment of the provider: wait and try again
                    await asyncio.sleep(min(2**attempt, MAX_WAIT))
                    continue
                if response.status_code == 429 or response.status_code >= 500:
                    await asyncio.sleep(_retry_after(response, attempt))
                    continue
                response.raise_for_status()
                data = response.json()
                self.calls += 1
                self.tokens += data.get("usage", {}).get("total_tokens", 0)
                return data["choices"][0]["message"]["content"]
        raise RuntimeError(f"judge unavailable after {MAX_ATTEMPTS} attempts")


class VertexJudge(GroqJudge):
    """The same GPT-OSS 120B as a model served by Vertex AI (OpenAI-compatible endpoint), with the
    project's Application Default Credentials: no API key, billed with the rest of the project."""

    provider = "Vertex AI"

    def __init__(self, model: str = VERTEX_JUDGE_MODEL, project: str | None = None):
        import google.auth

        self._credentials, default_project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.model_name = model
        self._url = VERTEX_URL.format(project=project or os.environ.get("GCP_PROJECT_ID") or default_project)
        self.calls = 0
        self.tokens = 0

    def _token(self) -> str:
        import google.auth.transport.requests

        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return self._credentials.token


def _retry_after(response: httpx.Response, attempt: int) -> float:
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = response.headers.get(header)
        if value:
            seconds = _seconds(value)
            if seconds is not None:
                return min(seconds + 0.5, MAX_WAIT)
    return min(2**attempt, MAX_WAIT)


def _seconds(value: str) -> float | None:
    """'7.66s', '2m59.5s', '12' -> seconds."""
    try:
        return float(value)
    except ValueError:
        pass
    match = re.fullmatch(r"(?:(\d+)m)?(?:([\d.]+)s)?(?:([\d.]+)ms)?", value.strip())
    if not match or not any(match.groups()):
        return None
    minutes, secs, millis = (float(g) if g else 0.0 for g in match.groups())
    return minutes * 60 + secs + millis / 1000


def _json_block(text: str) -> str:
    """The JSON object in the answer (some models wrap it in ```json fences, and GPT-OSS now and then
    as {"final": "<json>"}, its own output channel leaking into the answer)."""
    if not text:  # an empty answer is invalid JSON, so the caller retries or reports it
        return ""
    match = re.search(r"\{.*\}", text, re.S)
    block = match.group(0) if match else text
    try:
        data = json.loads(block)
    except ValueError:
        return block
    if isinstance(data, dict) and len(data) == 1 and next(iter(data)).startswith("final"):
        inner = next(iter(data.values()))  # {"final": "<json>"}, or {"final{": {...}} when the leak is worse
        return _json_block(inner) if isinstance(inner, str) else json.dumps(inner, ensure_ascii=False)
    return block


if __name__ == "__main__":  # quick check: uv run --group eval python -m evals.judge
    start = time.time()
    print(GroqJudge().generate('Devuelve {"score": 7}', schema=None), f"{time.time() - start:.1f}s")
