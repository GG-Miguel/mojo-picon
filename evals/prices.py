"""Prices of the chat models, in dollars per million tokens, to price an evaluation run.

Vertex AI, Standard on-demand, non-global endpoint (the EU multi-region one), context <= 200K tokens.
Source: cloud.google.com/vertex-ai/generative-ai/pricing, read on 2026-10-21. Gemini 3.8 Flash has a
promotional price until 31 Dec 2026 and doubles from 2027. Cached input is not separated: every input
token is priced as new, so the costs are an upper bound.
"""

from __future__ import annotations

PRICES = {  # model: (input, output), reasoning tokens are billed as output
    "gemini-3.8-flash": (0.825, 4.125),
    "gemini-3.5-flash": (1.65, 9.90),
    "gemini-3.5-flash-lite": (0.33, 2.75),
    "gemini-3.1-flash-lite": (0.275, 1.65),
}
PRICES_2027 = {**PRICES, "gemini-3.8-flash": (1.65, 8.25)}


def cost(tokens: dict[str, int], model: str, prices: dict = PRICES) -> float | None:
    """Dollars for {input, output} tokens of one model; None if the model has no price here."""
    if model not in prices:
        return None
    price_in, price_out = prices[model]
    return (tokens.get("input", 0) * price_in + tokens.get("output", 0) * price_out) / 1e6
