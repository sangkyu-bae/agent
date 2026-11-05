"""KbQuickSetupPolicy — agent-kb-quick-setup Design §3.1 / §9.4."""

import pytest
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.knowledge_base.quick_setup_policy import KbQuickSetupPolicy


class TestCollectionNameFor:
    def test_uses_prefix_and_first_eight_chars(self):
        kb_id = "3f1a9c2e-1111-2222-3333-444444444444"
        assert KbQuickSetupPolicy.collection_name_for(kb_id) == "kb-3f1a9c2e"

    def test_result_satisfies_collection_name_pattern(self):
        from src.domain.collection.policy import CollectionPolicy

        name = KbQuickSetupPolicy.collection_name_for("abcdef12-0000")
        CollectionPolicy.validate_name(name)  # raises if invalid

    def test_empty_kb_id_raises(self):
        with pytest.raises(ValueError):
            KbQuickSetupPolicy.collection_name_for("")


class TestScopeForVisibility:
    @pytest.mark.parametrize(
        ("visibility", "expected"),
        [
            ("private", CollectionScope.PERSONAL),
            ("department", CollectionScope.DEPARTMENT),
            ("public", CollectionScope.PUBLIC),
        ],
    )
    def test_maps_visibility(self, visibility, expected):
        assert KbQuickSetupPolicy.scope_for_visibility(visibility) == expected

    def test_unknown_visibility_raises(self):
        with pytest.raises(ValueError):
            KbQuickSetupPolicy.scope_for_visibility("friends")


class TestNextName:
    def test_first_attempt_is_base(self):
        assert KbQuickSetupPolicy.next_name("여신 상담봇 지식", 0) == "여신 상담봇 지식"

    def test_later_attempts_append_suffix(self):
        assert KbQuickSetupPolicy.next_name("A 지식", 1) == "A 지식 (2)"
        assert KbQuickSetupPolicy.next_name("A 지식", 19) == "A 지식 (20)"

    def test_suffix_keeps_within_max_length(self):
        base = "x" * KnowledgeBasePolicy.MAX_NAME_LENGTH
        name = KbQuickSetupPolicy.next_name(base, 1)
        assert len(name) <= KnowledgeBasePolicy.MAX_NAME_LENGTH
        assert name.endswith(" (2)")

    def test_attempts_beyond_limit_raise(self):
        with pytest.raises(ValueError):
            KbQuickSetupPolicy.next_name("A", KbQuickSetupPolicy.NAME_SUFFIX_MAX)


class TestValidateFiles:
    def test_accepts_supported_extensions_case_insensitive(self):
        KbQuickSetupPolicy.validate_files(
            ["a.pdf", "b.XLSX", "c.xls", "d.hwp", "e.HWPX"]
        )

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            KbQuickSetupPolicy.validate_files([])

    def test_rejects_over_limit(self):
        with pytest.raises(ValueError):
            KbQuickSetupPolicy.validate_files([f"{i}.pdf" for i in range(11)])

    def test_rejects_unsupported_extension_naming_it(self):
        with pytest.raises(ValueError, match="exe"):
            KbQuickSetupPolicy.validate_files(["a.pdf", "virus.exe"])
