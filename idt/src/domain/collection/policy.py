import re


class CollectionPolicy:
    PROTECTED_COLLECTIONS = frozenset({"documents"})
    NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")

    @staticmethod
    def validate_name(name: str) -> None:
        if not CollectionPolicy.NAME_PATTERN.match(name):
            raise ValueError(
                f"Invalid collection name: '{name}'. "
                "Must start with alphanumeric, 1-63 chars, only [a-zA-Z0-9_-]"
            )

    @staticmethod
    def can_delete(name: str, default_collection: str) -> None:
        if name in CollectionPolicy.PROTECTED_COLLECTIONS or name == default_collection:
            raise ValueError(
                f"Cannot delete protected collection: '{name}'"
            )
