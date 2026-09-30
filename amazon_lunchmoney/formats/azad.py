"""Azad order history CSV format.

Produced by the azad scraper (https://github.com/philipmulcahy/azad) in
"order" view, so each row is an order (not an item) and can be matched
against a Lunch Money charge.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ..amazon import AmazonTransaction
from .base import OrderHistoryAdapter


def _normalize_header(header: str) -> str:
    # 'Order ID' => 'orderid'
    return "".join(header.split()).lower()


class AzadAdapter(OrderHistoryAdapter):
    """Reads azad order-history CSV files."""

    name = "azad"

    def read(self, file_path: str | Path) -> list[AmazonTransaction]:
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
