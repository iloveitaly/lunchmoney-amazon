"""End-to-end CLI tests with mocked Lunch Money API and OpenAI."""

import datetime
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from amazon_lunchmoney.categorize import TransactionSummary
from amazon_lunchmoney.cli import cli
from amazon_lunchmoney.lunchmoney import Category, Transaction

CSV = """orderid,items,categories,to,date,total,shipping,shipping_refund,gift,tax,refund,payments
D01-1111111-1111111,Book,Books,__TO__,2024-12-01,25.99,0,0,0,0,0,"2024-12-01: $25.99; "
"""

CATEGORIES = [
    Category(id=10, name="Shopping"),
    Category(id=42, name="Books"),
    Category(id=7, name="Gifts"),
]

LM_TRANSACTIONS = [
    Transaction(
        id=100, date="2024-12-03", payee="Amazon", amount="25.99", category_id=10
    ),
    # already categorized: must be left alone and must not consume the match
    Transaction(
        id=101, date="2024-12-03", payee="Amazon", amount="25.99", category_id=42
    ),
]


class _FakeLMClient:
    last: "_FakeLMClient | None" = None

    def __init__(self, token: str) -> None:
        self.token = token
        self.updates: list[tuple[int, int | None, str | None]] = []
        self.date_range: tuple[datetime.date, datetime.date] | None = None
        _FakeLMClient.last = self

    def get_categories(self) -> list[Category]:
        return CATEGORIES

    def get_all_transactions(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[Transaction]:
        self.date_range = (start_date, end_date)
        return LM_TRANSACTIONS

    def update_transaction(
        self, transaction_id: int, *, category_id=None, notes=None
    ) -> bool:
        self.updates.append((transaction_id, category_id, notes))
        return True


class _FakeAI:
    calls: list[str]

    def __init__(self) -> None:
        self.calls = []

    def __call__(self, items: str, categories, client=None) -> TransactionSummary:
        self.calls.append(items)
        return TransactionSummary(id=42, summary="Reading material")


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "orders.csv"
    path.write_text(CSV.replace("__TO__", "Michael Bianco"))
    return path


@pytest.fixture
def fakes(monkeypatch) -> _FakeAI:
    monkeypatch.setattr("amazon_lunchmoney.cli.LunchMoneyClient", _FakeLMClient)
    monkeypatch.setattr("amazon_lunchmoney.cli.create_agent", lambda: object())
    fake_ai = _FakeAI()
    monkeypatch.setattr("amazon_lunchmoney.cli.ai_transaction_summary", fake_ai)
    return fake_ai


def test_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "--file" in result.output
    assert "--default-category" in result.output


def test_missing_required_options() -> None:
    result = CliRunner().invoke(cli, [])

    assert result.exit_code != 0


def test_missing_api_key(csv_file: Path, fakes: _FakeAI, monkeypatch) -> None:
    monkeypatch.delenv("LUNCH_MONEY_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["-f", str(csv_file), "-c", "Shopping"])

    assert result.exit_code == 1
    assert "Lunch Money API key not set" in result.output


def test_unknown_default_category(csv_file: Path, fakes: _FakeAI) -> None:
    result = CliRunner().invoke(cli, ["-f", str(csv_file), "-c", "Nope", "-k", "key"])

    assert result.exit_code == 1
    assert "Default category Nope not found" in result.output


def test_dry_run_updates_nothing(csv_file: Path, fakes: _FakeAI) -> None:
    result = CliRunner().invoke(
        cli, ["-f", str(csv_file), "-c", "Shopping", "-k", "key", "--dry-run"]
    )

    assert result.exit_code == 0
    assert _FakeLMClient.last is not None
    assert _FakeLMClient.last.updates == []
    # the AI still runs in dry-run mode
    assert fakes.calls == ["Book"]
    # query window is widened by a week on each side
    assert _FakeLMClient.last.date_range == (
        datetime.date(2024, 11, 24),
        datetime.date(2024, 12, 8),
    )


def test_categorizes_match_and_updates_notes(csv_file: Path, fakes: _FakeAI) -> None:
    result = CliRunner().invoke(
        cli, ["-f", str(csv_file), "-c", "Shopping", "-k", "key"]
    )

    assert result.exit_code == 0
    assert _FakeLMClient.last is not None
    assert _FakeLMClient.last.updates == [
        (100, 42, "#D01-1111111-1111111. Reading material")
    ]


def test_gift_order_uses_gifts_category(tmp_path: Path, fakes: _FakeAI) -> None:
    path = tmp_path / "orders.csv"
    path.write_text(CSV.replace("__TO__", "Jane Doe"))

    result = CliRunner().invoke(
        cli,
        ["-f", str(path), "-c", "Shopping", "-k", "key", "-n", "Michael Bianco"],
    )

    assert result.exit_code == 0
    assert fakes.calls == []
    assert _FakeLMClient.last is not None
    assert _FakeLMClient.last.updates == [(100, 7, "#D01-1111111-1111111")]


def test_mcp_format_reads_jsonl(tmp_path: Path, fakes: _FakeAI) -> None:
    path = tmp_path / "orders.jsonl"
    path.write_text(
        json.dumps(
            {
                "order_number": "112-7108886-6473855",
                "order_date": "December 1, 2024",
                "order_total": "$25.99",
                "items": ["Book"],
                "status": "Delivered",
                "returnable": False,
            }
        )
        + "\n"
    )

    result = CliRunner().invoke(
        cli,
        [
            "-f",
            str(path),
            "--format",
            "amazon-shopping-mcp",
            "-c",
            "Shopping",
            "-k",
            "key",
        ],
    )

    assert result.exit_code == 0
    assert _FakeLMClient.last is not None
    assert _FakeLMClient.last.updates == [
        (100, 42, "#112-7108886-6473855. Reading material")
    ]


def test_invalid_format_is_rejected(csv_file: Path, fakes: _FakeAI) -> None:
    result = CliRunner().invoke(
        cli, ["-f", str(csv_file), "--format", "bogus", "-c", "Shopping", "-k", "key"]
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.output


def test_version_option() -> None:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "amazon-lunchmoney, version" in result.output
    assert "model:" in result.output


def test_version_option_configured_model(monkeypatch) -> None:
    monkeypatch.setenv("AMAZON_LUNCHMONEY_MODEL", "openai:gpt-4o")
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "model: openai:gpt-4o" in result.output


def test_limit_option(tmp_path: Path, fakes: _FakeAI, monkeypatch) -> None:
    two_orders_csv = (
        CSV.replace("__TO__", "Michael Bianco")
        + 'D01-2222222-2222222,Pen,Office,Michael Bianco,2024-12-01,45.00,0,0,0,0,0,"2024-12-01: $45.00; "\n'
    )
    path = tmp_path / "orders.csv"
    path.write_text(two_orders_csv)

    txs = [
        Transaction(
            id=100,
            date="2024-12-03",
            payee="Amazon",
            amount="25.99",
            category_id=10,
        ),
        Transaction(
            id=101,
            date="2024-12-03",
            payee="Amazon",
            amount="45.00",
            category_id=10,
        ),
    ]
    monkeypatch.setattr(_FakeLMClient, "get_all_transactions", lambda self, s, e: txs)
    result = CliRunner().invoke(
        cli, ["-f", str(path), "-c", "Shopping", "-k", "key", "--limit", "1"]
    )
    assert result.exit_code == 0
    assert _FakeLMClient.last is not None
    # Only the first row from the CSV was processed
    assert len(_FakeLMClient.last.updates) == 1
    assert _FakeLMClient.last.updates[0][0] == 100
    assert fakes.calls == ["Book"]


def test_invalid_limit_rejected(csv_file: Path, fakes: _FakeAI) -> None:
    result = CliRunner().invoke(
        cli, ["-f", str(csv_file), "-c", "Shopping", "-k", "key", "--limit", "0"]
    )
    assert result.exit_code == 2
    assert "is not in the range" in result.output
