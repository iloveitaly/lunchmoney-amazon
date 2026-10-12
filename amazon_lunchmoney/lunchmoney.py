"""Lunch Money API client using lunchmoney-python (juftin/lunchmoney-clients)."""

from __future__ import annotations

import datetime
from typing import Any

import lunchmoney
from pydantic import BaseModel

from .log import log

BASE_URL = "https://api.lunchmoney.dev/v2"
PAGE_LIMIT = 1000


class Category(BaseModel):
    id: int
    name: str
    description: str | None = None
    is_income: bool = False
    archived: bool = False
    exclude_from_budget: bool = False
    is_group: bool = False

    @classmethod
    def from_api(cls, cat: Any) -> Category:
        if isinstance(cat, cls):
            return cat
        if isinstance(cat, dict):
            return cls(
                id=cat["id"],
                name=cat["name"],
                description=cat.get("description"),
                is_income=bool(cat.get("is_income", False)),
                archived=bool(cat.get("archived", False)),
                exclude_from_budget=bool(cat.get("exclude_from_budget", False)),
                is_group=bool(cat.get("is_group", False)),
            )
        return cls(
            id=cat.id,
            name=cat.name,
            description=cat.description,
            is_income=bool(cat.is_income),
            archived=bool(cat.archived),
            exclude_from_budget=bool(cat.exclude_from_budget),
            is_group=bool(cat.is_group),
        )


class Transaction(BaseModel):
    id: int
    date: str
    payee: str
    amount: str
    notes: str | None = None
    category_id: int | None = None
    is_group: bool = False
    group_id: int | None = None
    custom_metadata: dict[str, Any] | None = None

    @classmethod
    def from_api(cls, t: Any) -> Transaction:
        if isinstance(t, cls):
            return t
        if isinstance(t, dict):
            return cls(
                id=t["id"],
                date=str(t["date"]),
                payee=t["payee"],
                amount=str(t["amount"]),
                notes=t.get("notes"),
                category_id=t.get("category_id"),
                is_group=bool(t.get("is_group", t.get("is_group_parent", False))),
                group_id=t.get("group_id", t.get("group_parent_id")),
                custom_metadata=t.get("custom_metadata"),
            )
        date_val = getattr(t, "var_date", getattr(t, "date", None))
        if isinstance(date_val, (datetime.date, datetime.datetime)):
            date_str = date_val.isoformat()
        else:
            date_str = str(date_val or "")
        return cls(
            id=t.id,
            date=date_str,
            payee=t.payee,
            amount=str(t.amount),
            notes=t.notes,
            category_id=t.category_id,
            is_group=bool(getattr(t, "is_group_parent", getattr(t, "is_group", False))),
            group_id=getattr(t, "group_parent_id", getattr(t, "group_id", None)),
            custom_metadata=getattr(t, "custom_metadata", None),
        )


class LunchMoneyClient:
    def __init__(
        self,
        token: str,
        base_url: str = BASE_URL,
        api_client: lunchmoney.ApiClient | None = None,
    ) -> None:
        if api_client is not None:
            self._api_client = api_client
        else:
            configuration = lunchmoney.Configuration(
                host=base_url,
                access_token=token,
            )
            self._api_client = lunchmoney.ApiClient(configuration)

        self.categories_api = lunchmoney.CategoriesApi(self._api_client)
        self.transactions_bulk_api = lunchmoney.TransactionsBulkApi(self._api_client)
        self.transactions_api = lunchmoney.TransactionsApi(self._api_client)

    def get_categories(self) -> list[Category]:
        response = self.categories_api.get_all_categories(format="flattened")
        cats = response.categories or []
        return [Category.from_api(c) for c in cats]

    def get_all_transactions(
        self, start_date: datetime.date, end_date: datetime.date
    ) -> list[Transaction]:
        """Fetch every transaction in the date range, following pagination."""
        transactions: list[Transaction] = []
        offset = 0

        while True:
            response = self.transactions_bulk_api.get_all_transactions(
                start_date=start_date,
                end_date=end_date,
                include_metadata=True,
                limit=PAGE_LIMIT,
                offset=offset,
            )
            txs = response.transactions or []
            transactions.extend(Transaction.from_api(t) for t in txs)

            if not response.has_more:
                break
            offset += PAGE_LIMIT

        return transactions

    def update_transaction(
        self,
        transaction_id: int,
        *,
        category_id: int | None = None,
        notes: str | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> bool:
        "Update a transaction's category, notes, and/or custom metadata"
        params = {
            k: v
            for k, v in {
                "category_id": category_id,
                "notes": notes,
                "custom_metadata": custom_metadata,
            }.items()
            if v is not None
        }
        update_obj = lunchmoney.UpdateTransactionObject(**params)
        # the sdk's response map only includes 201 so 200 responses deserialize to none
        try:
            response = self.transactions_api.update_transaction_with_http_info(
                id=transaction_id,
                update_transaction_object=update_obj,
            )
        except lunchmoney.ApiException as err:
            log.error(
                "lunch money api error updating transaction",
                id=transaction_id,
                status=err.status,
                reason=err.reason,
                body=err.body,
            )
            return False

        if not 200 <= response.status_code < 300:
            log.error(
                "lunch money api update failed",
                id=transaction_id,
                status=response.status_code,
                body=response.raw_data.decode("utf-8", errors="replace"),
            )
            return False

        return True
