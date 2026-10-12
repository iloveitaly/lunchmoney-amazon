"""Tests for the shared Amazon order model and matching filters."""

import datetime

from amazon_lunchmoney.amazon import (
    AmazonTransaction,
    date_range,
    filter_transactions_after_date,
    is_matchable,
)


def test_is_matchable() -> None:
    base = AmazonTransaction(
        orderid="1", items="Book", to="Mike", date="2024-01-01", total="9.99"
    )
    assert is_matchable(base) is True

    # $0 orders (gift card) have no matching LM entry
    assert is_matchable(AmazonTransaction(**{**base.__dict__, "total": "0"})) is False
    # unusable dates
    for date in ("pending", "?", ""):
        assert (
            is_matchable(AmazonTransaction(**{**base.__dict__, "date": date})) is False
        )
    # unscraped items
    for items in ("pending", ""):
        assert (
            is_matchable(AmazonTransaction(**{**base.__dict__, "items": items}))
            is False
        )
    # unparseable totals can never match a charge amount
    for total in ("", "pending", "abc"):
        assert (
            is_matchable(AmazonTransaction(**{**base.__dict__, "total": total}))
            is False
        )


def test_date_range() -> None:
    transactions = [
        AmazonTransaction(date="2024-01-05"),
        AmazonTransaction(date="2024-01-01"),
        AmazonTransaction(date="2024-01-10"),
    ]
    assert date_range(transactions) == (
        datetime.date(2024, 1, 1),
        datetime.date(2024, 1, 10),
    )


def test_filter_transactions_after_date() -> None:
    transactions = [
        AmazonTransaction(orderid="1", date="2024-01-01"),
        AmazonTransaction(orderid="2", date="2024-01-05"),
        AmazonTransaction(orderid="3", date="2024-01-10"),
    ]
    filtered = filter_transactions_after_date(transactions, datetime.date(2024, 1, 5))
    assert [t.orderid for t in filtered] == ["2", "3"]
