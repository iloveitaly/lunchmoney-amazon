"""Parsing and filtering of Amazon order history CSV exports.

The CSV is produced by the azad scraper
(https://github.com/philipmulcahy/azad) in "order" view, so each row is an
order (not an item) and can be matched against a Lunch Money charge.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass
from pathlib import Path


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


def _normalize_header(header: str) -> str:
    # 'Order ID' => 'orderid'
    return "".join(header.split()).lower()


def read_csv(file_path: str | Path) -> list[AmazonTransaction]:
    """Read an azad order-history CSV file into a list of transactions."""
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        reader.fieldnames = [_normalize_header(h) for h in reader.fieldnames]
        return [
            AmazonTransaction.from_row({k: (v or "") for k, v in row.items()})
            for row in reader
            if any((v or "").strip() for v in row.values())
        ]


def is_matchable(transaction: AmazonTransaction) -> bool:
    """Whether an order can possibly be matched to a Lunch Money transaction.

    Filters out:
      - $0 orders (paid by gift card), which have no matching entry in LM
      - orders without a usable date
      - orders with a "pending" item list (could not be scraped)
    """
    return (
        transaction.total != "0"
        and transaction.date not in ("pending", "?", "")
        and transaction.items not in ("pending", "")
    )


def date_range(
    transactions: list[AmazonTransaction],
) -> tuple[datetime.date, datetime.date]:
    """Return the (min, max) order date across the given transactions."""
    dates = [datetime.date.fromisoformat(t.date) for t in transactions]
    return min(dates), max(dates)
