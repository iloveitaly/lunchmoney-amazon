"""Tests for the Lunch Money API client (mocked HTTP)."""

import datetime
import json

import httpx

from amazon_lunchmoney.lunchmoney import LunchMoneyClient


def _client(handler) -> LunchMoneyClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="https://dev.lunchmoney.app", transport=transport
    )
    return LunchMoneyClient(token="test-token", client=http_client)


def test_get_categories() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/categories"
        return httpx.Response(
            200,
            json={
                "categories": [
                    {"id": 1, "name": "Shopping", "description": "Stuff"},
                    {"id": 2, "name": "Group", "is_group": True},
                ]
            },
        )

    categories = _client(handler).get_categories()

    assert [c.name for c in categories] == ["Shopping", "Group"]
    assert categories[0].description == "Stuff"
    assert categories[1].is_group is True


def test_get_all_transactions_pages_until_exhausted() -> None:
    seen_offsets: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/transactions"
        params = dict(request.url.params)
        assert params["start_date"] == "2024-12-01"
        assert params["end_date"] == "2024-12-31"
        seen_offsets.append(params.get("offset"))
        if params.get("offset") == "0":
            return httpx.Response(
                200,
                json={
                    "transactions": [
                        {
                            "id": 1,
                            "date": "2024-12-02",
                            "payee": "Amazon",
                            "amount": "9.99",
                        }
                    ],
                    "has_more": True,
                },
            )
        return httpx.Response(200, json={"transactions": [], "has_more": False})

    transactions = _client(handler).get_all_transactions(
        datetime.date(2024, 12, 1), datetime.date(2024, 12, 31)
    )

    assert [t.id for t in transactions] == [1]
    assert seen_offsets == ["0", "1000"]


def test_update_transaction_sends_category_and_notes() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path == "/v1/transactions/123"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"updated": True})

    updated = _client(handler).update_transaction(123, category_id=5, notes="#D01-1")

    assert updated is True
    assert bodies == [{"category_id": 5, "notes": "#D01-1"}]


def test_update_transaction_omits_unset_fields() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"updated": False})

    updated = _client(handler).update_transaction(123, notes="#D01-1")

    assert updated is False
    assert bodies == [{"notes": "#D01-1"}]
