"""AI categorization, gift detection, and note building."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from openai import OpenAI

from .amazon import AmazonTransaction
from .lunchmoney import Category

log = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
MAX_TOKENS = 50

# from docs: https://lunchmoney.dev/#update-transaction
NOTE_LIMIT = 350


@dataclass
class TransactionSummary:
    id: int | None
    summary: str


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


def ai_transaction_summary(
    transaction_items: str,
    categories: list[Category],
    client: OpenAI | None = None,
) -> TransactionSummary:
    """Ask the AI to pick a category id and summarize the purchased items."""
    prompt = generate_summary_prompt(transaction_items, categories_json(categories))
    client = client or OpenAI()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
        temperature=0,
    )

    content = response.choices[0].message.content

    if not content:
        return TransactionSummary(id=None, summary="")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        log.warning("AI returned invalid JSON: %s", content)
        return TransactionSummary(id=None, summary="")

    try:
        chosen_id = int(parsed["id"])
    except (TypeError, ValueError, KeyError):
        chosen_id = None

    summary = str(parsed.get("summary") or "")

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
    """Build the updated LM note: order number plus an AI summary, truncated."""
    # None would print as "None", which is why we need ""
    new_note = f"#{orderid} {existing_notes or ''}".strip()

    if summary:
        new_note += f". {summary}"

    return new_note[:NOTE_LIMIT]


def should_update_note(existing_notes: str | None, orderid: str) -> bool:
    return orderid not in (existing_notes or "")
