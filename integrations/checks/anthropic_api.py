"""The Anthropic integration test (prds/integrations-tab-plan.md § 3; the check
list Doug approved 11-13-26, phase 3 stopping point 1).

Read only through the Models API: **no message is ever sent**, so the test
costs nothing. Checks, in order:

1. **Settings present** — the API key.
2. **List the models** — ``client.models.list()``: proves the key. Fact: how
   many models the key can use.
3. **The configured models** — ``client.models.retrieve(id)`` for the summary
   model and the research model. A model that does not exist is failed while
   its feature (``comms_ai_summary``, ``enrichment_ai``) is on, and only
   reported while it is off. Facts: each model's display name.

The integration agent model joins check 3 in phase 6, with its setting.
Written to the ``claude-api`` skill: the official SDK, its typed exceptions
most specific first, no retries inside a 12-second check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from integrations.testing import FAILED, OK, UNKNOWN, Blocked, Check, Context, run_checks

#: (setting, its label, the switch whose feature uses it, that feature's name)
MODELS: tuple[tuple[str, str, str, str], ...] = (
    ("summary_model", "Summary model", "comms_ai_summary", "email summaries"),
    ("enrichment_ai_model", "Research model", "enrichment_ai", "AI research"),
)


def _default_client(settings: Any) -> Any:
    import anthropic

    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=10.0, max_retries=0)


@dataclass
class Deps:
    client: Callable[[Any], Any] = _default_client


def _answer(exc: Exception, what: str) -> tuple[str, str]:
    import anthropic

    if isinstance(exc, anthropic.AuthenticationError):
        return FAILED, f"Anthropic refused the API key (HTTP 401) reading {what}. Check the key in the Claude Console."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return FAILED, f"The API key is not allowed to read {what} (HTTP 403)."
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return UNKNOWN, f"Could not read {what}: {type(exc).__name__}."
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500:
            return UNKNOWN, f"Anthropic could not answer for {what} just now (HTTP {exc.status_code})."
        return FAILED, f"Anthropic refused to show {what} (HTTP {exc.status_code})."
    return UNKNOWN, f"Could not read {what}: {type(exc).__name__}: {exc}"


async def _settings(ctx: Context) -> tuple[str, str]:
    if not (ctx.settings.anthropic_api_key or "").strip():
        return FAILED, "Not set: the Anthropic API key."
    ctx.state["client"] = ctx.deps.client(ctx.settings)
    return OK, "The Anthropic API key is set."


async def _list(ctx: Context) -> tuple[str, str]:
    if "client" not in ctx.state:
        raise Blocked("Not checked: the API key is not set (check 1).")
    try:
        page = await ctx.state["client"].models.list(limit=100)
    except Exception as exc:  # noqa: BLE001
        return _answer(exc, "the list of models")
    data = getattr(page, "data", None)
    if not isinstance(data, list):
        return UNKNOWN, "Anthropic answered without a list of models; its API may have changed."
    more = " or more" if getattr(page, "has_more", False) else ""
    ctx.fact("Models available", f"{len(data)}{more}")
    ctx.state["key_ok"] = True
    return OK, f"Anthropic accepted the key: {len(data)}{more} models available."


async def _configured(ctx: Context) -> tuple[str, str]:
    import anthropic

    if not ctx.state.get("key_ok"):
        raise Blocked("Not checked: the key could not be confirmed (check 2).")
    client = ctx.state["client"]
    failed: list[str] = []
    unknown: list[str] = []
    noted: list[str] = []
    for key, label, switch, feature in MODELS:
        model_id = (getattr(ctx.settings, key, "") or "").strip()
        on = bool(getattr(ctx.settings, switch, False))
        if not model_id:
            ctx.fact(label, "not set")
            (failed if on else noted).append(f"the {label.lower()} is not set")
            continue
        try:
            model = await client.models.retrieve(model_id)
        except anthropic.NotFoundError:
            ctx.fact(label, f"{model_id}: does not exist")
            msg = f"{model_id} ({label.lower()}) does not exist"
            if on:
                failed.append(msg + f", and {feature} is on")
            else:
                noted.append(msg + f"; {feature} is off")
            continue
        except Exception as exc:  # noqa: BLE001
            outcome, detail = _answer(exc, model_id)
            ctx.fact(label, f"{model_id}: not checked")
            (failed if outcome == FAILED else unknown).append(detail)
            continue
        name = getattr(model, "display_name", "") or model_id
        ctx.fact(label, f"{model_id} ({name})")
    if failed:
        return FAILED, "; ".join(failed) + "."
    if unknown:
        return UNKNOWN, "; ".join(unknown)
    if noted:
        return OK, "Each model in use exists. Note: " + "; ".join(noted) + "."
    return OK, "Each configured model exists."


CHECKS: list[Check] = [
    Check("settings", "Settings present", _settings),
    Check("models", "List the models", _list),
    Check("configured", "The configured models", _configured),
]


async def run(settings: Any, deps: Optional[Deps] = None) -> dict[str, Any]:
    ctx = Context(settings=settings, deps=deps or Deps())
    return await run_checks("anthropic", CHECKS, ctx)
