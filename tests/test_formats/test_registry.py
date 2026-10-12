"""Tests for the format adapter registry."""

import json
from pathlib import Path

import pytest

from amazon_lunchmoney.formats import (
    ADAPTERS,
    FORMAT_AMAZON_SHOPPING_MCP,
    FORMAT_AZAD,
    AmazonShoppingMcpAdapter,
    AzadAdapter,
    get_adapter,
    read_orders,
)


def test_registry_covers_all_formats() -> None:
    assert set(ADAPTERS) == {FORMAT_AZAD, FORMAT_AMAZON_SHOPPING_MCP}
    assert isinstance(ADAPTERS[FORMAT_AZAD], AzadAdapter)
    assert isinstance(ADAPTERS[FORMAT_AMAZON_SHOPPING_MCP], AmazonShoppingMcpAdapter)


def test_get_adapter_unknown_format() -> None:
    with pytest.raises(ValueError, match="Unknown order history format: bogus"):
        get_adapter("bogus")


def test_read_orders_dispatches_on_format(tmp_path: Path) -> None:
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "orderid,items,to,date,total\n"
        "D01-1,Book,Mike,2024-01-01,9.99\n"
        "D01-2,Pen,Mike,2024-01-02,1.99\n"
    )
    jsonl_path = tmp_path / "orders.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "order_number": "112-7108886-6473855",
                "order_date": "September 28, 2021",
                "order_total": "$14.00",
                "items": ["Backpack"],
                "status": "Delivered",
                "returnable": False,
            }
        )
        + "\n"
    )

    assert len(read_orders(csv_path, FORMAT_AZAD)) == 2
    assert len(read_orders(csv_path)) == 2
    assert len(read_orders(jsonl_path, FORMAT_AMAZON_SHOPPING_MCP)) == 1


def test_read_orders_sorts_newest_first(tmp_path: Path) -> None:
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text(
        "orderid,items,to,date,total\n"
        "old-1,Book,Mike,2021-01-01,9.99\n"
        "new-1,Pen,Mike,2024-12-01,1.99\n"
        "mid-1,Toy,Mike,2023-06-15,4.99\n"
    )

    transactions = read_orders(csv_path, FORMAT_AZAD)
    assert [t.orderid for t in transactions] == ["new-1", "mid-1", "old-1"]
