"""Unit tests for src.shared.string_case.snake_to_camel."""

from src.shared.string_case import snake_to_camel


def test_empty_string_returns_empty() -> None:
    assert snake_to_camel("") == ""


def test_single_word_unchanged() -> None:
    assert snake_to_camel("hello") == "hello"


def test_basic_snake_to_camel() -> None:
    assert snake_to_camel("hello_world") == "helloWorld"


def test_multiple_words() -> None:
    assert snake_to_camel("user_first_name") == "userFirstName"


def test_consecutive_underscores_are_safe() -> None:
    assert snake_to_camel("hello__world") == "helloWorld"


def test_leading_underscore_is_safe() -> None:
    assert snake_to_camel("_hello_world") == "helloWorld"


def test_trailing_underscore_is_safe() -> None:
    assert snake_to_camel("hello_world_") == "helloWorld"


def test_already_camel_unchanged() -> None:
    assert snake_to_camel("helloWorld") == "helloWorld"
