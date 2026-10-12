"""Tests for the Lunch Money API client."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import lunchmoney

from amazon_lunchmoney.lunchmoney import LunchMoneyClient


def test_get_categories() -> None:
    client = LunchMoneyClient(token="test-token")
    cat1 = SimpleNamespace(
        id=1,
        name="Shopping",
        description="Stuff",
        is_income=False,
        archived=False,
        exclude_from_budget=False,
        is_group=False,
    )
    cat2 = SimpleNamespace(
        id=2,
        name="Group",
        description=None,
        is_income=False,
        archived=False,
        exclude_from_budget=False,
        is_group=True,
    )
    client.categories_api.get_all_categories = MagicMock(
        return_value=SimpleNamespace(categories=[cat1, cat2])
    )

    categories = client.get_categories()

    assert [c.name for c in categories] == ["Shopping", "Group"]
    assert categories[0].description == "Stuff"
    assert categories[1].is_group is True


def test_get_all_transactions_pages_until_exhausted() -> None:
    client = LunchMoneyClient(token="test-token")
    tx1 = SimpleNamespace(
        id=1,
        var_date=datetime.date(2024, 12, 2),
        payee="Amazon",
        amount="9.99",
        notes=None,
        category_id=None,
        is_group_parent=False,
        group_parent_id=None,
    )

    seen_offsets: list[int] = []

    def mock_get_all(start_date, end_date, limit, offset, include_metadata=None):
        assert start_date == datetime.date(2024, 12, 1)
        assert end_date == datetime.date(2024, 12, 31)
        assert include_metadata is True
        seen_offsets.append(offset)
        if offset == 0:
            return SimpleNamespace(transactions=[tx1], has_more=True)
        return SimpleNamespace(transactions=[], has_more=False)

    client.transactions_bulk_api.get_all_transactions = MagicMock(
        side_effect=mock_get_all
    )

    transactions = client.get_all_transactions(
        datetime.date(2024, 12, 1), datetime.date(2024, 12, 31)
    )

    assert [t.id for t in transactions] == [1]
    assert seen_offsets == [0, 1000]


def test_update_transaction_sends_category_and_notes() -> None:
    client = LunchMoneyClient(token="test-token")
    update_calls: list[tuple[int, object]] = []

    def mock_update(id, update_transaction_object):
        update_calls.append((id, update_transaction_object))
        return SimpleNamespace(status_code=200, raw_data=b"", data=None)

    client.transactions_api.update_transaction_with_http_info = MagicMock(
        side_effect=mock_update
    )

    updated = client.update_transaction(123, category_id=5, notes="#D01-1")

    assert updated is True
    assert len(update_calls) == 1
    assert update_calls[0][0] == 123
    assert update_calls[0][1].category_id == 5
    assert update_calls[0][1].notes == "#D01-1"


def test_update_transaction_omits_unset_fields() -> None:
    client = LunchMoneyClient(token="test-token")
    update_calls: list[tuple[int, object]] = []

    def mock_update(id, update_transaction_object):
        update_calls.append((id, update_transaction_object))
        return SimpleNamespace(status_code=200, raw_data=b"", data=None)

    client.transactions_api.update_transaction_with_http_info = MagicMock(
        side_effect=mock_update
    )

    updated = client.update_transaction(123, notes="#D01-1")

    assert updated is True
    assert len(update_calls) == 1
    assert update_calls[0][0] == 123
    assert update_calls[0][1].notes == "#D01-1"
    dumped = update_calls[0][1].model_dump(exclude_unset=True)
    assert "category_id" not in dumped


def test_update_transaction_sends_custom_metadata() -> None:
    client = LunchMoneyClient(token="test-token")
    update_calls: list[tuple[int, object]] = []

    def mock_update(id, update_transaction_object):
        update_calls.append((id, update_transaction_object))
        return SimpleNamespace(status_code=200, raw_data=b"", data=None)

    client.transactions_api.update_transaction_with_http_info = MagicMock(
        side_effect=mock_update
    )

    updated = client.update_transaction(
        123, custom_metadata={"amazon_order_id": "D01-1111111"}
    )

    assert updated is True
    assert len(update_calls) == 1
    assert update_calls[0][1].custom_metadata == {"amazon_order_id": "D01-1111111"}


def test_update_transaction_handles_api_exception() -> None:
    client = LunchMoneyClient(token="test-token")
    err = lunchmoney.ApiException(status=400, reason="Bad Request", body="invalid")
    client.transactions_api.update_transaction_with_http_info = MagicMock(
        side_effect=err
    )

    updated = client.update_transaction(123, notes="fail")

    assert updated is False
