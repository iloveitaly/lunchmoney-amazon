"""Shared Amazon order model and matching filters.

Format-specific parsing lives in `amazon_lunchmoney.formats`; every adapter
produces these transactions so matching works the same regardless of source.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class AmazonTransaction:
    orderid: str = ""
    items: str = ""
    categories: str = ""
    to: str = ""
    date: str = ""
    total: str = ""
    shipping: str = ""
    shipping_refund: str = ""
    gift: str = ""
    tax: str = ""
    refund: str = ""
    payments: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> AmazonTransaction:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v or "" for k, v in row.items() if k in known})


def _has_parseable_total(transaction: AmazonTransaction) -> bool:
    try:
        float(transaction.total)
        return True
    except ValueError:
        return False


def is_matchable(transaction: AmazonTransaction) -> bool:
    """Whether an order can possibly be matched to a Lunch Money transaction.

    Filters out:
      - $0 orders (paid by gift card), which have no matching entry in LM
      - orders without a usable date
      - orders with a "pending" item list (could not be scraped)
      - orders without a parseable total (e.g. cancelled MCP orders)
    """
    return (
        transaction.total != "0"
        and transaction.date not in ("pending", "?", "")
        and transaction.items not in ("pending", "")
        and _has_parseable_total(transaction)
    )


def date_range(
    transactions: list[AmazonTransaction],
) -> tuple[datetime.date, datetime.date]:
    """Return the (min, max) order date across the given transactions."""
    dates = [datetime.date.fromisoformat(t.date) for t in transactions]
    return min(dates), max(dates)
