"""amazon-shopping-mcp purchases JSONL format.

Each line is an OrderSummary object produced by
https://github.com/iloveitaly/amazon-shopping-mcp
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

from ..amazon import AmazonTransaction
from .base import OrderHistoryAdapter

log = logging.getLogger(__name__)


def _parse_date(value: object) -> str:
    """Parse a displayed order date ("September 28, 2021") into ISO format."""
    if not isinstance(value, str):
        return ""
    try:
        # only the calendar date is used, so no timezone applies
        parsed = datetime.datetime.strptime(  # noqa: DTZ007
            value.strip(), "%B %d, %Y"
        )
        return parsed.date().isoformat()
    except ValueError:
        return ""


def _parse_total(value: object) -> str:
    """Normalize a displayed order total ("$1,234.56") into a plain number."""
    if not isinstance(value, str):
        return ""
    return value.strip().replace("$", "").replace(",", "")


def _row_to_transaction(row: dict[str, Any]) -> AmazonTransaction:
    items = row.get("items")
    return AmazonTransaction(
        orderid=str(row.get("order_number") or ""),
        items="; ".join(items) if isinstance(items, list) else "",
        date=_parse_date(row.get("order_date")),
        total=_parse_total(row.get("order_total")),
    )


class AmazonShoppingMcpAdapter(OrderHistoryAdapter):
    """Reads amazon-shopping-mcp purchases JSONL files.

    Blank lines are skipped; malformed lines are skipped with a warning.
    The format carries no recipient data, so gift detection is inactive
    for these orders.
    """

    name = "amazon-shopping-mcp"

    def read(self, file_path: str | Path) -> list[AmazonTransaction]:
        transactions: list[AmazonTransaction] = []
        with open(file_path, encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("skipping malformed JSON on line %s", line_number)
                    continue
                if not isinstance(row, dict):
                    log.warning("skipping non-object JSON on line %s", line_number)
                    continue
                transactions.append(_row_to_transaction(row))
        return transactions
