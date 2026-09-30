"""Interface for order history format adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..amazon import AmazonTransaction


class OrderHistoryAdapter(ABC):
    """Reads one order history file format into shared transactions."""

    name: str

    @abstractmethod
    def read(self, file_path: str | Path) -> list[AmazonTransaction]:
        """Read an order history file into a list of transactions."""
        ...
