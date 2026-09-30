"""Minimal Lunch Money API v1 client.

Only the endpoints needed for categorization are implemented:
https://lunchmoney.dev
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://dev.lunchmoney.app"
PAGE_LIMIT = 1000


@dataclass
class Category:
    id: int
    name: str
    description: str | None = None
    is_income: bool = False
    archived: bool = False
    exclude_from_budget: bool = False
    is_group: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Category:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description"),
            is_income=bool(data.get("is_income", False)),
            archived=bool(data.get("archived", False)),
            exclude_from_budget=bool(data.get("exclude_from_budget", False)),
            is_group=bool(data.get("is_group", False)),
        )


@dataclass
class Transaction:
    id: int
    date: str
    payee: str
    amount: str
    notes: str | None = None
    category_id: int | None = None
    is_group: bool = False
    group_id: int | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Transaction:
        return cls(
            id=data["id"],
            date=data["date"],
            payee=data["payee"],
            amount=str(data["amount"]),
            notes=data.get("notes"),
            category_id=data.get("category_id"),
            is_group=bool(data.get("is_group", False)),
            group_id=data.get("group_id"),
        )


class LunchMoneyClient:
    def __init__(
        self,
        token: str,
        base_url: str = BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    def get_categories(self) -> list[Category]:
        response = self._client.get("/v1/categories")
        response.raise_for_status()
        return [Category.from_api(c) for c in response.json()["categories"]]

    def get_all_transactions(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[Transaction]:
        """Fetch every transaction in the date range, following pagination."""
        transactions: list[Transaction] = []
        offset = 0

        while True:
            response = self._client.get(
                "/v1/transactions",
                params={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "limit": PAGE_LIMIT,
                    "offset": offset,
                },
            )
            response.raise_for_status()
            payload = response.json()
            transactions.extend(
                Transaction.from_api(t) for t in payload["transactions"]
            )

            if not payload.get("has_more"):
                break
            offset += PAGE_LIMIT

        return transactions

    def update_transaction(
        self,
        transaction_id: int,
        *,
        category_id: int | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update a transaction's category and/or notes. Returns `updated`."""
        payload: dict[str, Any] = {}
        if category_id is not None:
            payload["category_id"] = category_id
        if notes is not None:
            payload["notes"] = notes

        response = self._client.put(f"/v1/transactions/{transaction_id}", json=payload)
        response.raise_for_status()
        return bool(response.json().get("updated", False))
