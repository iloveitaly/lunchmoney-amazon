"""Tests for the amazon-shopping-mcp JSONL adapter."""

import json
from pathlib import Path

from amazon_lunchmoney.amazon import is_matchable
from amazon_lunchmoney.formats.amazon_shopping_mcp import AmazonShoppingMcpAdapter


def _mcp_row(**overrides) -> dict:
    row = {
        "order_number": "112-7108886-6473855",
        "order_date": "September 28, 2021",
        "order_total": "$14.00",
        "items": ["Backpack", "Pencil"],
        "status": "Delivered",
        "returnable": False,
    }
    return {**row, **overrides}


def _write_jsonl(tmp_path: Path, rows: list) -> Path:
    path = tmp_path / "orders.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def test_read_parses_rows(tmp_path: Path) -> None:
    transactions = AmazonShoppingMcpAdapter().read(_write_jsonl(tmp_path, [_mcp_row()]))

    assert len(transactions) == 1
    txn = transactions[0]
    assert txn.orderid == "112-7108886-6473855"
    assert txn.items == "Backpack; Pencil"
    assert txn.date == "2021-09-28"
    assert txn.total == "14.00"
    # the format carries no recipient or category data
    assert txn.to == ""
    assert txn.categories == ""


def test_read_strips_currency_formatting(tmp_path: Path) -> None:
    transactions = AmazonShoppingMcpAdapter().read(
        _write_jsonl(tmp_path, [_mcp_row(order_total=" $1,234.56 ")])
    )

    assert transactions[0].total == "1234.56"


def test_read_tolerates_missing_fields(tmp_path: Path) -> None:
    transactions = AmazonShoppingMcpAdapter().read(
        _write_jsonl(
            tmp_path,
            [
                _mcp_row(order_total=None),
                _mcp_row(order_date="not a date"),
                _mcp_row(order_date=None, items=[]),
            ],
        )
    )

    assert [t.total for t in transactions] == ["", "14.00", "14.00"]
    assert [t.date for t in transactions] == ["2021-09-28", "", ""]
    assert transactions[2].items == ""
    # none of these rows can be matched
    assert not any(is_matchable(t) for t in transactions)


def test_read_skips_blank_and_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "orders.jsonl"
    path.write_text(
        "\n".join(
            [
                "",
                json.dumps(_mcp_row()),
                "not json",
                json.dumps(["not", "an", "object"]),
                json.dumps(_mcp_row(order_number="112-0000000-0000000")),
                "",
            ]
        )
    )

    transactions = AmazonShoppingMcpAdapter().read(path)

    assert [t.orderid for t in transactions] == [
        "112-7108886-6473855",
        "112-0000000-0000000",
    ]
