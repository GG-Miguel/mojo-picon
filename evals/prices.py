"""Prices of the chat models, in dollars per million tokens, to price an evaluation run.

Vertex AI, Standard on-demand, non-global endpoint (the EU multi-region one), context <= 200K tokens.
Source: cloud.google.com/vertex-ai/generative-ai/pricing, read on 2026-10-21. The promotional prices of
Gemini 3.8 Flash (until 31 Dec 2026) and Gemini 4 Argon (until 30 Nov 2026) are a 50 % credit on the
next month's bill, not a lower price on the invoice; they double afterwards. Cached input is not separated: every input
token is priced as new, so the costs are an upper bound.
"""

from __future__ import annotations

PRICES = {  # model: (input, output), reasoning tokens are billed as output
    "gemini-3.8-flash": (0.825, 4.125),
    "gemini-3.5-flash": (1.65, 9.90),
    "gemini-3.5-flash-lite": (0.33, 2.75),
    "gemini-3.1-flash-lite": (0.275, 1.65),
    "gemini-4-argon": (2.2, 11.0),  # promotional until 30 Nov 2026; (4.4, 22.0) from 1 Dec
}
PRICES_2027 = {**PRICES, "gemini-3.8-flash": (1.65, 8.25), "gemini-4-argon": (4.4, 22.0)}


def cost(tokens: dict[str, int], model: str, prices: dict = PRICES) -> float | None:
    """Dollars for {input, output} tokens of one model; None if the model has no price here."""
    if model not in prices:
        return None
    price_in, price_out = prices[model]
    return (tokens.get("input", 0) * price_in + tokens.get("output", 0) * price_out) / 1e6
