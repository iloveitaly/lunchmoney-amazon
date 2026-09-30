import logging
import os
import sys

import pydantic_ai

pydantic_ai.BANNER_ENABLED = False

from .cli import cli as cli_command
from .config import (
    DEFAULT_MODEL_NAME,
    MODEL_NAME,
    get_model_name,
    map_ai_key,
    update_env_variables,
)
from .version import __version__

update_env_variables()

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_MODEL_NAME",
    "MODEL_NAME",
    "__version__",
    "get_model_name",
    "main",
    "map_ai_key",
    "update_env_variables",
]


def main() -> None:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"amazon-lunchmoney version {__version__}")
        print(f"model: {get_model_name()}")
        sys.exit(0)

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    cli_command()
