import pytest

from src.domain.doc_browse.policies import DocumentDeletePolicy
from src.domain.doc_browse.schemas import DocumentMetadata


@pytest.fixture
def policy():
    return DocumentDeletePolicy()


@pytest.fixture
def sample_metadata():
    return DocumentMetadata(
        document_id="doc-123",
        collection_name="test-collection",
        filename="test.pdf",
        category="general",
        user_id="42",
        chunk_count=10,
        chunk_strategy="parent_child",
    )


class TestDocumentDeletePolicy:

    def test_uploader_can_delete_own_document(self, policy, sample_metadata):
        assert policy.can_delete(
            user_id="42",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=999,
        ) is True

    def test_collection_owner_can_delete(self, policy, sample_metadata):
        assert policy.can_delete(
            user_id="100",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=100,
        ) is True

    def test_admin_can_always_delete(self, policy, sample_metadata):
        assert policy.can_delete(
            user_id="999",
            user_role="admin",
            document_metadata=sample_metadata,
            collection_owner_id=888,
        ) is True

    def test_unrelated_user_cannot_delete(self, policy, sample_metadata):
        assert policy.can_delete(
            user_id="999",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=888,
        ) is False

    def test_collection_owner_none_only_uploader_allowed(
        self, policy, sample_metadata
    ):
        assert policy.can_delete(
            user_id="42",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=None,
        ) is True

    def test_collection_owner_none_non_uploader_denied(
        self, policy, sample_metadata
    ):
        assert policy.can_delete(
            user_id="999",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=None,
        ) is False

    def test_user_id_str_int_comparison_for_owner(self, policy, sample_metadata):
        assert policy.can_delete(
            user_id="100",
            user_role="user",
            document_metadata=sample_metadata,
            collection_owner_id=100,
        ) is True
