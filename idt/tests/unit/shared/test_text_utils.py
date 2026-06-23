"""Unit tests for src.shared.text_utils.slugify."""

import pytest

from src.shared.text_utils import slugify


def test_empty_string_returns_empty() -> None:
    assert slugify("") == ""


def test_whitespace_only_returns_empty() -> None:
    assert slugify("   ") == ""


def test_spaces_become_hyphens() -> None:
    assert slugify("hello world") == "hello-world"


def test_uppercase_is_lowercased() -> None:
    assert slugify("Hello World") == "hello-world"


def test_special_characters_are_removed() -> None:
    assert slugify("hello@#$world!") == "helloworld"


def test_korean_characters_are_removed() -> None:
    assert slugify("안녕 world 하세요") == "world"


def test_alphanumeric_and_hyphen_preserved() -> None:
    assert slugify("abc-123 DEF") == "abc-123-def"


def test_collapses_consecutive_spaces_and_trims() -> None:
    assert slugify("  multiple   spaces  ") == "multiple-spaces"
