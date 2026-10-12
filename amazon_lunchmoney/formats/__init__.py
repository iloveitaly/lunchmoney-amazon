"""Order history format adapters and registry."""

from __future__ import annotations

from pathlib import Path

from ..amazon import AmazonTransaction
from .amazon_shopping_mcp import AmazonShoppingMcpAdapter
from .azad import AzadAdapter
from .base import OrderHistoryAdapter

FORMAT_AZAD = AzadAdapter.name
FORMAT_AMAZON_SHOPPING_MCP = AmazonShoppingMcpAdapter.name

ADAPTERS: dict[str, OrderHistoryAdapter] = {
    AzadAdapter.name: AzadAdapter(),
    AmazonShoppingMcpAdapter.name: AmazonShoppingMcpAdapter(),
}

__all__ = [
    "ADAPTERS",
    "FORMAT_AMAZON_SHOPPING_MCP",
    "FORMAT_AZAD",
    "AmazonShoppingMcpAdapter",
    "AzadAdapter",
    "OrderHistoryAdapter",
    "get_adapter",
    "read_orders",
]


def get_adapter(file_format: str) -> OrderHistoryAdapter:
    """Return the adapter for the given format name."""
    try:
        return ADAPTERS[file_format]
    except KeyError:
        raise ValueError(f"Unknown order history format: {file_format}") from None


def read_orders(
    file_path: str | Path, file_format: str = FORMAT_AZAD
) -> list[AmazonTransaction]:
    """Read an order history file in the given format into transactions, newest first."""
    transactions = get_adapter(file_format).read(file_path)
    # sort newest first so recent transactions are prioritized
    return sorted(
        transactions,
        key=lambda t: t.date if t.date and t.date[0].isdigit() else "",
        reverse=True,
    )
