"""AI categorization, gift detection, and note building."""

from __future__ import annotations

import json
from typing import Any

import pydantic_ai
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelSettings
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
)
from pydantic_ai.models import Model
from pydantic_ai.models.google import GoogleModel

from .amazon import AmazonTransaction
from .config import DEFAULT_MODEL_NAME, get_model_name, update_env_variables
from .log import log
from .lunchmoney import Category

pydantic_ai.BANNER_ENABLED = False

MODEL = DEFAULT_MODEL_NAME

# from docs: https://lunchmoney.dev/#update-transaction
NOTE_LIMIT = 350


class TransactionSummary(BaseModel):
    id: int | None = Field(
        default=None,
        description="The ID of the category that best matches the list of items, or null if no category matches.",
    )
    summary: str = Field(
        default="",
        description="A concise summary of the items purchased in a handful of words.",
    )


def prompt_categories(categories: list[Category]) -> list[Category]:
    """Categories worth offering to the AI: budgeted, active expense categories."""
    return [
        c
        for c in categories
        if not c.is_income
        and not c.archived
        and not c.exclude_from_budget
        and not c.is_group
    ]


def categories_json(categories: list[Category]) -> str:
    # limit the data passed to the AI
    return json.dumps(
        [{"id": c.id, "name": c.name, "description": c.description} for c in categories]
    )


def generate_summary_prompt(transaction_items: str, categories: str) -> str:
    return f"""
Here is a list of categories in a personal finance tool:

```json
{categories}
```

Here is a description of a group of items purchased from Amazon:

```
{transaction_items}
```

Pick the category that best matches the list of items above. Include only the ID in an `id` JSON field.

Summary the items purchased into a handful of words. Include this summary in a `summary` JSON field.

Here is an example response:

```json
{{
  "id": 123,
  "summary": "Online groceries"
}}
```

Include only raw JSON, no codefences.
"""


def create_agent(
    model: str | Model | None = None,
) -> Agent[None, TransactionSummary]:
    """Create a Pydantic AI agent configured for transaction categorization."""
    model_name_or_obj = model or get_model_name()
    return Agent(
        model_name_or_obj,
        output_type=TransactionSummary,
        system_prompt=(
            "You are a personal finance assistant. Categorize Amazon purchases into one of the provided categories "
            "and provide a short concise summary (a handful of words) of the items purchased. "
            "Pick the category that best matches the list of items. If no category matches, set id to null."
        ),
    )


def ai_transaction_summary(
    transaction_items: str,
    categories: list[Category],
    agent: Any = None,
) -> TransactionSummary:
    """Ask the AI to pick a category id and summarize the purchased items."""
    update_env_variables()
    prompt = generate_summary_prompt(transaction_items, categories_json(categories))

    if isinstance(agent, Model):
        agent_instance = create_agent(model=agent)
    elif agent is None:
        agent_instance = create_agent()
    else:
        agent_instance = agent

    model_settings: ModelSettings | None = None
    if isinstance(agent_instance.model, GoogleModel) or (
        isinstance(agent_instance.model, str)
        and (
            agent_instance.model.startswith("google:")
            or agent_instance.model.startswith("gemini:")
        )
    ):
        # Gemini 3.7+ rejects thinking_level=minimal; low is the cheapest
        # level still accepted across current Gemini models.
        # https://ai.pydantic.dev/models/google/#configure-thinking
        model_settings = ModelSettings(thinking="low")

    try:
        result = agent_instance.run_sync(prompt, model_settings=model_settings)
        summary_output = result.output
    except (ModelHTTPError, ModelAPIError, UnexpectedModelBehavior) as e:
        log.warning("ai model request failed", error=e)
        return TransactionSummary(id=None, summary="")

    if summary_output is None:
        return TransactionSummary(id=None, summary="")

    if isinstance(summary_output, str):
        try:
            parsed = json.loads(summary_output)
            chosen_id = int(parsed["id"]) if parsed.get("id") is not None else None
            summary = str(parsed.get("summary") or "")
        except (json.JSONDecodeError, ValueError, KeyError):
            log.warning("ai returned invalid json", output=summary_output)
            return TransactionSummary(id=None, summary="")
    elif isinstance(summary_output, TransactionSummary):
        chosen_id = summary_output.id
        summary = summary_output.summary or ""
    elif isinstance(summary_output, dict):
        try:
            chosen_id = (
                int(summary_output["id"])
                if summary_output.get("id") is not None
                else None
            )
        except (TypeError, ValueError):
            chosen_id = None
        summary = str(summary_output.get("summary") or "")
    else:
        chosen_id = getattr(summary_output, "id", None)
        summary = getattr(summary_output, "summary", "") or ""

    if chosen_id is None or all(c.id != chosen_id for c in categories):
        return TransactionSummary(id=None, summary=summary)

    return TransactionSummary(id=chosen_id, summary=summary)


def category_name_to_id(categories: list[Category], category_name: str) -> int | None:
    """Find a category ID by exact name match, ignoring group categories."""
    return next(
        (c.id for c in categories if not c.is_group and c.name == category_name),
        None,
    )


def order_is_gift(transaction: AmazonTransaction, owner_names: list[str]) -> bool:
    """An order is a gift if its recipient is not one of the account owners."""
    # in some cases '0' is returned by the scraper, we want to exclude these values
    if not owner_names or not transaction.to or transaction.to == "0":
        return False

    return transaction.to.lower().strip() not in owner_names


def build_note(orderid: str, existing_notes: str | None, summary: str | None) -> str:
    "Build the updated LM note with order number at the end"
    if existing_notes and orderid in existing_notes:
        return existing_notes

    parts: list[str] = []
    if existing_notes and existing_notes.strip():
        parts.append(existing_notes.strip())

    if summary and summary.strip() and summary.strip() not in parts:
        parts.append(summary.strip())

    if not parts:
        return f"#{orderid}"[:NOTE_LIMIT]

    prefix = ". ".join(parts)
    suffix = f" #{orderid}"
    max_prefix_len = NOTE_LIMIT - len(suffix)
    if len(prefix) > max_prefix_len:
        prefix = prefix[:max_prefix_len].rstrip()

    return f"{prefix}{suffix}"


def should_update_note(existing_notes: str | None, orderid: str) -> bool:
    return orderid not in (existing_notes or "")
