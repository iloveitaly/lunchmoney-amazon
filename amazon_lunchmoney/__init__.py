import sys

import pydantic_ai

pydantic_ai.BANNER_ENABLED = False

from .cli import cli as cli_command
from .config import get_model_name, update_env_variables
from .log import setup_logging
from .version import __version__

update_env_variables()


def main() -> None:
    if "--version" in sys.argv or "-V" in sys.argv:
        print(f"amazon-lunchmoney version {__version__}")
        print(f"model: {get_model_name()}")
        sys.exit(0)

    setup_logging()
    cli_command()
