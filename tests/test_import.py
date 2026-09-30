"""Test amazon-lunchmoney."""

import amazon_lunchmoney


def test_import() -> None:
    """Test that the  can be imported."""
    assert isinstance(amazon_lunchmoney.__name__, str)


def test_version() -> None:
    """Test that the version is available."""
    assert isinstance(amazon_lunchmoney.__version__, str)
