import pytest

from src.domain.collection.policy import CollectionPolicy


class TestValidateName:
    @pytest.mark.parametrize(
        "name",
        ["documents", "my-collection", "test_col", "A", "a1b2c3", "x" * 63],
    )
    def test_valid_names_pass(self, name: str) -> None:
        CollectionPolicy.validate_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "",
            "-starts-with-dash",
            "_starts-with-underscore",
            "has space",
            "has.dot",
            "x" * 64,
            "special!char",
        ],
    )
    def test_invalid_names_raise(self, name: str) -> None:
        with pytest.raises(ValueError, match="Invalid collection name"):
            CollectionPolicy.validate_name(name)


class TestCanDelete:
    def test_protected_collection_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot delete protected collection"):
            CollectionPolicy.can_delete("documents", "documents")

    def test_default_collection_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot delete protected collection"):
            CollectionPolicy.can_delete("my-default", "my-default")

    def test_normal_collection_passes(self) -> None:
        CollectionPolicy.can_delete("my-collection", "documents")
