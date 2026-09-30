"""Tests for Amazon CSV parsing and filtering."""

import datetime
from pathlib import Path

from amazon_lunchmoney.amazon import (
    AmazonTransaction,
    date_range,
    is_matchable,
    read_csv,
)

SAMPLE_CSV = """orderid,items,categories,to,date,total,shipping,shipping_refund,gift,tax,refund,payments
D01-1111111-1111111,"Elf; ",,0,2021-12-17,0,0,0,0,3.99,0,"2021-12-17: $0.00; "
D01-2222222-2222222,"Book; Pen; ",Books,Michael Bianco,2024-12-01,25.99,0,0,0,0,0,"2024-12-01: $25.99; "
"""


def _write_csv(tmp_path: Path, content: str = SAMPLE_CSV) -> Path:
    path = tmp_path / "orders.csv"
    path.write_text(content)
    return path


def test_read_csv_parses_rows(tmp_path: Path) -> None:
    transactions = read_csv(_write_csv(tmp_path))

    assert len(transactions) == 2
    assert transactions[1].orderid == "D01-2222222-2222222"
    assert transactions[1].items == "Book; Pen; "
    assert transactions[1].to == "Michael Bianco"
    assert transactions[1].date == "2024-12-01"
    assert transactions[1].total == "25.99"


def test_read_csv_normalizes_headers(tmp_path: Path) -> None:
    content = "Order ID,Items,To,Date,Total\nD01-1,Book,Mike,2024-01-01,9.99\n"
    transactions = read_csv(_write_csv(tmp_path, content))

    assert len(transactions) == 1
    assert transactions[0].orderid == "D01-1"
    assert transactions[0].total == "9.99"


def test_read_csv_skips_blank_lines(tmp_path: Path) -> None:
    content = "orderid,items,to,date,total\nD01-1,Book,Mike,2024-01-01,9.99\n\n"
    assert len(read_csv(_write_csv(tmp_path, content))) == 1


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
