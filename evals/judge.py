"""The judge for G-Eval: GPT-OSS 120B on Groq (free tier), another model family than the agents (ADR-13).

It only sees synthetic test cases, never user data, so a provider outside the EU is acceptable here.
On a rate limit (HTTP 429) it waits as long as Groq says and retries the SAME model: switching judges
in the middle of a run would make the scores of different variants incomparable.
"""

from __future__ import annotations

import asyncio
import os
import re
import time

import httpx
from deepeval.models.base_model import DeepEvalBaseLLM
from pydantic import BaseModel

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
JUDGE_MODEL = "openai/gpt-oss-120b"
MAX_ATTEMPTS = 8
USER_AGENT = "mojo-picon-eval/0.1"  # Groq and other gateways reject generic HTTP-library agents


class GroqJudge(DeepEvalBaseLLM):
    def __init__(self, model: str = JUDGE_MODEL, api_key: str | None = None):
        self.model_name = model
        self._key = api_key or os.environ["GROQ_API_KEY"]
        self.calls = 0
        self.tokens = 0

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"{self.model_name} (Groq)"

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
        headers = {"authorization": f"Bearer {self._key}", "user-agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=120) as client:
            for attempt in range(MAX_ATTEMPTS):
                response = await client.post(GROQ_URL, json=body, headers=headers)
                if response.status_code == 429 or response.status_code >= 500:
                    await asyncio.sleep(_retry_after(response, attempt))
                    continue
                response.raise_for_status()
                data = response.json()
                self.calls += 1
                self.tokens += data.get("usage", {}).get("total_tokens", 0)
                return data["choices"][0]["message"]["content"]
        raise RuntimeError(f"judge unavailable after {MAX_ATTEMPTS} attempts")


def _retry_after(response: httpx.Response, attempt: int) -> float:
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = response.headers.get(header)
        if value:
            seconds = _seconds(value)
            if seconds is not None:
                return min(seconds + 0.5, 90)
    return min(2**attempt, 60)


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
    """The JSON object in the answer (some models wrap it in ```json fences)."""
    match = re.search(r"\{.*\}", text, re.S)
    return match.group(0) if match else text


if __name__ == "__main__":  # quick check: uv run --group eval python -m evals.judge
    start = time.time()
    print(GroqJudge().generate('Devuelve {"score": 7}', schema=None), f"{time.time() - start:.1f}s")
