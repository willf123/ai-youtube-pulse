"""Claude API helper: one structured-output call with retries, refusal handling and cost logging."""
from __future__ import annotations

from typing import Type, TypeVar

import anthropic
from pydantic import BaseModel

from common import get_logger, load_config

log = get_logger("claude")
T = TypeVar("T", bound=BaseModel)

# $ per 1M tokens (input, output) — for the run-cost log line only.
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}

_client: anthropic.Anthropic | None = None
spent_usd = 0.0


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=4, timeout=900)
    return _client


def structured(system: str, prompt: str, schema: Type[T], effort: str = "medium",
               max_tokens: int = 32000, model: str | None = None) -> T:
    """Ask Claude for JSON matching `schema` (a Pydantic model) and return the parsed object."""
    global spent_usd
    model = model or load_config()["claude"]["model"]
    # Long outputs: stream so the request never hits an HTTP timeout.
    with client().beta.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": effort},
        output_format=schema,
        # Server-side fallback: if a safety classifier declines, the API retries on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        resp = stream.get_final_message()

    u = resp.usage
    pin, pout = PRICES.get(model, (4.0, 20.0))
    cost = (u.input_tokens * pin + u.output_tokens * pout) / 1e6
    spent_usd += cost
    log.info("%s: in=%d out=%d tokens (~$%.3f, run total ~$%.2f) stop=%s",
             schema.__name__, u.input_tokens, u.output_tokens, cost, spent_usd, resp.stop_reason)

    if resp.stop_reason == "refusal":
        details = getattr(resp, "stop_details", None)
        raise RuntimeError(f"Claude declined the {schema.__name__} request: {details}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"{schema.__name__} output hit max_tokens={max_tokens}; raise it or shrink the batch")
    parsed = getattr(resp, "parsed_output", None)
    if parsed is None:
        text = next((b.text for b in resp.content if b.type == "text"), "")
        parsed = schema.model_validate_json(text)
    return parsed
