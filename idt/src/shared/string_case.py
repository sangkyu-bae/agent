"""String case conversion utilities (pure functions, no side effects)."""


def snake_to_camel(text: str) -> str:
    """Convert a snake_case string to camelCase.

    Leading, trailing, and consecutive underscores are handled safely by
    ignoring empty segments. A string with no underscores (including an
    already camelCase string) is returned unchanged.

    Args:
        text: The snake_case input string.

    Returns:
        The camelCase representation of ``text``.

    Examples:
        >>> snake_to_camel("user_first_name")
        'userFirstName'
        >>> snake_to_camel("_hello__world_")
        'helloWorld'
    """
    parts = [segment for segment in text.split("_") if segment]
    if not parts:
        return ""
    head, *tail = parts
    return head + "".join(word[:1].upper() + word[1:] for word in tail)
