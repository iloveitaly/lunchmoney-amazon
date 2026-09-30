"""Tests for AI categorization, gift detection, and note building."""

import json

from amazon_lunchmoney.amazon import AmazonTransaction
from amazon_lunchmoney.categorize import (
    NOTE_LIMIT,
    ai_transaction_summary,
    build_note,
    categories_json,
    category_name_to_id,
    generate_summary_prompt,
    order_is_gift,
    prompt_categories,
    should_update_note,
)
from amazon_lunchmoney.lunchmoney import Category


def _category(id: int, name: str, **overrides) -> Category:
    defaults = {
        "description": None,
        "is_income": False,
        "archived": False,
        "exclude_from_budget": False,
        "is_group": False,
    }
    return Category(id=id, name=name, **{**defaults, **overrides})


class _FakeMessage:
    def __init__(self, content: str | None) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str | None) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str | None) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str | None) -> None:
        self._content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCompletion(self._content)


class _FakeChat:
    def __init__(self, content: str | None) -> None:
        self.completions = _FakeCompletions(content)


class _FakeOpenAI:
    def __init__(self, content: str | None) -> None:
        self.chat = _FakeChat(content)


def test_prompt_categories_filters() -> None:
    categories = [
        _category(1, "Shopping"),
        _category(2, "Paycheck", is_income=True),
        _category(3, "Old", archived=True),
        _category(4, "Transfer", exclude_from_budget=True),
        _category(5, "Group", is_group=True),
    ]

    result = prompt_categories(categories)

    assert [c.name for c in result] == ["Shopping"]


def test_categories_json_limits_fields() -> None:
    parsed = json.loads(
        categories_json([_category(1, "Shopping", description="Stuff")])
    )

    assert parsed == [{"id": 1, "name": "Shopping", "description": "Stuff"}]


def test_generate_summary_prompt_includes_items_and_categories() -> None:
    prompt = generate_summary_prompt("Book; Pen; ", '[{"id": 1}]')

    assert "Book; Pen; " in prompt
    assert '[{"id": 1}]' in prompt


def test_category_name_to_id() -> None:
    categories = [_category(1, "Shopping"), _category(2, "Shopping", is_group=True)]

    assert category_name_to_id(categories, "Shopping") == 1
    assert category_name_to_id(categories, "Missing") is None


def test_order_is_gift() -> None:
    assert order_is_gift(AmazonTransaction(to="Jane Doe"), ["michael bianco"]) is True
    assert (
        order_is_gift(AmazonTransaction(to="Michael Bianco"), ["michael bianco"])
        is False
    )
    # matching is case-insensitive (owners are normalized by the caller)
    assert (
        order_is_gift(AmazonTransaction(to="michael bianco"), ["michael bianco"])
        is False
    )
    # no owners configured means no gifts
    assert order_is_gift(AmazonTransaction(to="Jane Doe"), []) is False
    # scraper gaps are not gifts
    assert order_is_gift(AmazonTransaction(to="0"), ["michael bianco"]) is False
    assert order_is_gift(AmazonTransaction(to=""), ["michael bianco"]) is False


def test_build_note() -> None:
    assert build_note("D01-1", None, None) == "#D01-1"
    assert build_note("D01-1", "existing", None) == "#D01-1 existing"
    assert build_note("D01-1", None, "Online groceries") == "#D01-1. Online groceries"


def test_build_note_truncates() -> None:
    note = build_note("D01-1", "x" * 500, "y" * 100)

    assert len(note) == NOTE_LIMIT
    assert note.startswith("#D01-1")


def test_should_update_note() -> None:
    assert should_update_note(None, "D01-1") is True
    assert should_update_note("something else", "D01-1") is True
    assert should_update_note("#D01-1 already noted", "D01-1") is False


def test_ai_summary_accepts_known_category() -> None:
    categories = [_category(42, "Books")]
    client = _FakeOpenAI('{"id": 42, "summary": "Reading material"}')

    result = ai_transaction_summary("Book", categories, client)  # type: ignore[arg-type]

    assert result.id == 42
    assert result.summary == "Reading material"
    assert client.chat.completions.calls[0]["model"] == "gpt-4o-mini"
    assert client.chat.completions.calls[0]["temperature"] == 0


def test_ai_summary_rejects_unknown_category_but_keeps_summary() -> None:
    categories = [_category(42, "Books")]
    client = _FakeOpenAI('{"id": 999, "summary": "Reading material"}')

    result = ai_transaction_summary("Book", categories, client)  # type: ignore[arg-type]

    assert result.id is None
    assert result.summary == "Reading material"


def test_ai_summary_handles_empty_and_invalid_responses() -> None:
    categories = [_category(42, "Books")]

    assert ai_transaction_summary("Book", categories, _FakeOpenAI(None)).summary == ""  # type: ignore[arg-type]

    result = ai_transaction_summary("Book", categories, _FakeOpenAI("not json"))  # type: ignore[arg-type]
    assert result.id is None
    assert result.summary == ""

    result = ai_transaction_summary("Book", categories, _FakeOpenAI('{"id": "abc"}'))  # type: ignore[arg-type]
    assert result.id is None
