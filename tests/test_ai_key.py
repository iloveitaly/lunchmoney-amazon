import os
from unittest.mock import patch

from amazon_lunchmoney import update_env_variables


def test_universal_ai_key_mapping():
    # Test mapping for different providers
    test_cases = [
        ("openai:gpt-4", "OPENAI_API_KEY"),
        ("anthropic:claude-3", "ANTHROPIC_API_KEY"),
        ("gemini:gemini-1.5-pro", "GOOGLE_API_KEY"),
        ("google:gemini-3-flash", "GOOGLE_API_KEY"),
        ("azure:gpt-4", "AZURE_OPENAI_API_KEY"),
        ("groq:llama3", "GROQ_API_KEY"),
    ]

    for model, target_var in test_cases:
        with patch.dict(
            os.environ,
            {
                "AMAZON_LUNCHMONEY_AI_KEY": "test-key-123",
                "AMAZON_LUNCHMONEY_MODEL": model,
            },
            clear=True,
        ):
            update_env_variables()
            assert os.environ.get(target_var) == "test-key-123", (
                f"Failed for model {model}"
            )


def test_ai_key_precedence():
    # Specific AMAZON_LUNCHMONEY_<PROVIDER>_API_KEY should take precedence over AMAZON_LUNCHMONEY_AI_KEY
    with patch.dict(
        os.environ,
        {
            "AMAZON_LUNCHMONEY_AI_KEY": "universal-key",
            "AMAZON_LUNCHMONEY_OPENAI_API_KEY": "specific-key",
            "AMAZON_LUNCHMONEY_MODEL": "openai:gpt-4",
        },
        clear=True,
    ):
        update_env_variables()
        # AMAZON_LUNCHMONEY_OPENAI_API_KEY maps to OPENAI_API_KEY first
        # Then AMAZON_LUNCHMONEY_AI_KEY tries to set it but should skip if already present
        assert os.environ.get("OPENAI_API_KEY") == "specific-key"


def test_standard_key_precedence():
    # Standard keys already in environment should take precedence over universal shortcut
    with patch.dict(
        os.environ,
        {
            "AMAZON_LUNCHMONEY_AI_KEY": "universal-key",
            "OPENAI_API_KEY": "existing-key",
            "AMAZON_LUNCHMONEY_MODEL": "openai:gpt-4",
        },
        clear=True,
    ):
        update_env_variables()
        assert os.environ.get("OPENAI_API_KEY") == "existing-key"
