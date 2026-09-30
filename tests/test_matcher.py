"""Tests for matching Lunch Money charges to Amazon orders."""

from amazon_lunchmoney.amazon import AmazonTransaction
from amazon_lunchmoney.lunchmoney import Transaction
from amazon_lunchmoney.matcher import find_matching_transaction, normalize_amount


def _lm(amount: str, date: str = "2024-12-03") -> Transaction:
    return Transaction(id=1, date=date, payee="Amazon", amount=amount, category_id=10)


def _am(orderid: str, total: str, date: str = "2024-12-01") -> AmazonTransaction:
    return AmazonTransaction(orderid=orderid, total=total, date=date, items="Book")


def test_normalize_amount() -> None:
    assert normalize_amount("25.99") == "25.99"
    assert normalize_amount("25.9") == "25.90"
    assert normalize_amount("25") == "25.00"
    assert normalize_amount("not-a-number") is None


def test_match_by_amount() -> None:
    remaining = [_am("A", "10.00"), _am("B", "25.99")]

    match = find_matching_transaction(_lm("25.99"), remaining)

    assert match is not None
    assert match.orderid == "B"


def test_match_amount_formatting_insensitive() -> None:
    remaining = [_am("A", "25.9")]

    match = find_matching_transaction(_lm("25.90"), remaining)

    assert match is not None
    assert match.orderid == "A"


def test_no_match_returns_none() -> None:
    remaining = [_am("A", "10.00")]

    assert find_matching_transaction(_lm("25.99"), remaining) is None
    # non-matches leave the pool untouched
    assert len(remaining) == 1


def test_prefers_closest_date() -> None:
    remaining = [
        _am("far", "25.99", date="2024-11-01"),
        _am("near", "25.99", date="2024-12-02"),
    ]

    match = find_matching_transaction(_lm("25.99", date="2024-12-03"), remaining)

    assert match is not None
    assert match.orderid == "near"


def test_match_is_removed_from_pool() -> None:
    remaining = [_am("A", "25.99"), _am("B", "25.99", date="2024-12-02")]

    first = find_matching_transaction(_lm("25.99"), remaining)
    second = find_matching_transaction(_lm("25.99"), remaining)
    third = find_matching_transaction(_lm("25.99"), remaining)

    assert first is not None and second is not None
    assert first.orderid != second.orderid
    assert third is None
    assert remaining == []
