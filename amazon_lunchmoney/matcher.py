"""Matching Lunch Money charges to Amazon orders."""

from __future__ import annotations

import datetime

from .amazon import AmazonTransaction
from .lunchmoney import Transaction

DATE_TOLERANCE_DAYS = 5


def normalize_amount(value: str) -> str | None:
    """Normalize a money string to two decimals for comparison, if parseable."""
    try:
        return f"{float(value):.2f}"
    except ValueError:
        return None


def find_matching_transaction(
    transaction: Transaction, remaining_amazon_transactions: list[AmazonTransaction]
) -> AmazonTransaction | None:
    """Find the Amazon order matching a Lunch Money charge.

    First matches on amount and date proximity, then prefers the closest date.
    The match is removed from `remaining_amazon_transactions` so it can't match twice.
    """
    target_amount = normalize_amount(transaction.amount)
    if target_amount is None:
        return None

    transaction_date = datetime.date.fromisoformat(transaction.date)

    possible_matches = [
        t
        for t in remaining_amazon_transactions
        if normalize_amount(t.total) == target_amount
        and abs((transaction_date - datetime.date.fromisoformat(t.date)).days)
        <= DATE_TOLERANCE_DAYS
    ]

    if not possible_matches:
        return None

    # if there are multiple possible matches, prefer the closest date
    possible_matches.sort(
        key=lambda t: abs((transaction_date - datetime.date.fromisoformat(t.date)).days)
    )

    best = possible_matches[0]
    index = next(
        i
        for i, t in enumerate(remaining_amazon_transactions)
        if t.orderid.strip() == best.orderid.strip()
    )

    return remaining_amazon_transactions.pop(index)
