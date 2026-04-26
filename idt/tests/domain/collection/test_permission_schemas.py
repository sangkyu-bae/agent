"""Domain schema tests for collection permissions — mock 금지."""
import pytest

from src.domain.collection.permission_schemas import (
    CollectionPermission,
    CollectionScope,
)


class TestCollectionScope:
    def test_values(self) -> None:
        assert CollectionScope.PERSONAL.value == "PERSONAL"
        assert CollectionScope.DEPARTMENT.value == "DEPARTMENT"
        assert CollectionScope.PUBLIC.value == "PUBLIC"

    def test_is_str_enum(self) -> None:
        assert isinstance(CollectionScope.PERSONAL, str)

    def test_from_string(self) -> None:
        assert CollectionScope("PERSONAL") == CollectionScope.PERSONAL
        assert CollectionScope("DEPARTMENT") == CollectionScope.DEPARTMENT
        assert CollectionScope("PUBLIC") == CollectionScope.PUBLIC

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            CollectionScope("INVALID")


class TestCollectionPermission:
    def test_required_fields(self) -> None:
        perm = CollectionPermission(
            collection_name="my-docs",
            owner_id=1,
            scope=CollectionScope.PERSONAL,
        )
        assert perm.collection_name == "my-docs"
        assert perm.owner_id == 1
        assert perm.scope == CollectionScope.PERSONAL
        assert perm.department_id is None
        assert perm.id is None

    def test_department_scope_with_dept_id(self) -> None:
        perm = CollectionPermission(
            collection_name="team-docs",
            owner_id=2,
            scope=CollectionScope.DEPARTMENT,
            department_id="dept-001",
        )
        assert perm.scope == CollectionScope.DEPARTMENT
        assert perm.department_id == "dept-001"

    def test_public_scope(self) -> None:
        perm = CollectionPermission(
            collection_name="shared",
            owner_id=3,
            scope=CollectionScope.PUBLIC,
        )
        assert perm.scope == CollectionScope.PUBLIC
