import logging
import os
import sys

from .cli import cli as cli_command
from .version import __version__

log = logging.getLogger(__name__)

__all__ = ["__version__", "main"]


def main() -> None:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"amazon-lunchmoney version {__version__}")
        sys.exit(0)

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    cli_command()
