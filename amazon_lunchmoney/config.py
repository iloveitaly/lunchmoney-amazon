"""Configuration and environment variable management."""

from __future__ import annotations

import os

DEFAULT_MODEL_NAME = "google:gemini-3.8-flash"
MODEL_NAME = os.environ.get("AMAZON_LUNCHMONEY_MODEL", DEFAULT_MODEL_NAME)


def map_ai_key(ai_key: str, model_name: str) -> None:
    """Maps the universal AMAZON_LUNCHMONEY_AI_KEY to the provider-specific environment variable name.

    This allows a single configuration variable to work across different providers (OpenAI,
    Anthropic, Gemini, etc.) by detecting the provider from the model name.

    Specific keys (e.g. OPENAI_API_KEY) already present in the environment take precedence.
    """
    provider = model_name.split(":")[0]

    # Map the universal key to the provider-specific environment variable name
    # https://ai.pydantic.dev/models/overview/
    mapping = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "gemini": "GOOGLE_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "cohere": "CO_API_KEY",
    }

    if (target_key := mapping.get(provider)) and target_key not in os.environ:
        os.environ[target_key] = ai_key


def update_env_variables() -> None:
    """Allow keys specific to AMAZON_LUNCHMONEY to be set globally so project-specific keys can be used for AI calls."""
    global MODEL_NAME
    prefix = "AMAZON_LUNCHMONEY_"
    for key in list(os.environ.keys()):
        if key.startswith(prefix):
            base_key = key[len(prefix) :]
            os.environ[base_key] = os.environ[key]

    MODEL_NAME = os.environ.get("AMAZON_LUNCHMONEY_MODEL", DEFAULT_MODEL_NAME)

    if ai_key := os.environ.get("AMAZON_LUNCHMONEY_AI_KEY") or os.environ.get("AI_KEY"):
        model_name = (
            os.environ.get("AMAZON_LUNCHMONEY_MODEL")
            or os.environ.get("MODEL")
            or DEFAULT_MODEL_NAME
        )
        map_ai_key(ai_key, model_name)


def get_model_name() -> str:
    return (
        os.environ.get("AMAZON_LUNCHMONEY_MODEL")
        or os.environ.get("MODEL")
        or MODEL_NAME
    )


update_env_variables()
