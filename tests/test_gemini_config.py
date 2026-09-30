from unittest.mock import MagicMock, patch

from pydantic_ai.models.google import GoogleModel

from amazon_lunchmoney.categorize import TransactionSummary, ai_transaction_summary
from amazon_lunchmoney.lunchmoney import Category


@patch("amazon_lunchmoney.categorize.create_agent")
def test_ai_transaction_summary_gemini_thinking_config(mock_create_agent):
    mock_agent_instance = MagicMock()
    mock_agent_instance.model = MagicMock(spec=GoogleModel)
    mock_agent_instance.run_sync.return_value = MagicMock(
        output=TransactionSummary(id=42, summary="test message")
    )
    mock_create_agent.return_value = mock_agent_instance

    categories = [Category(id=42, name="Shopping")]
    ai_transaction_summary("test items", categories)

    _args, kwargs = mock_agent_instance.run_sync.call_args
    assert kwargs["model_settings"]["thinking"] == "low"


@patch("amazon_lunchmoney.categorize.create_agent")
def test_ai_transaction_summary_non_gemini_no_config(mock_create_agent):
    mock_agent_instance = MagicMock()
    mock_agent_instance.model = MagicMock()
    mock_agent_instance.run_sync.return_value = MagicMock(
        output=TransactionSummary(id=42, summary="test message")
    )
    mock_create_agent.return_value = mock_agent_instance

    categories = [Category(id=42, name="Shopping")]
    ai_transaction_summary("test items", categories)

    _args, kwargs = mock_agent_instance.run_sync.call_args
    assert kwargs.get("model_settings") is None
