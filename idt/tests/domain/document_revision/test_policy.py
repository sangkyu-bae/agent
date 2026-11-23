"""RevisionPolicy — 대상 검증·버전 번호·되돌리기·연결·점수·verdict (Design §3.2, §4.2, §10.5)."""

from datetime import datetime

import pytest
from src.domain.document_revision.errors import (
    RevisionLinkInvalidError,
    RevisionTargetInvalidError,
    RollbackNotAllowedError,
)
from src.domain.document_revision.policy import RevisionPolicy
from src.domain.document_revision.value_objects import (
    CheckVerdict,
    DocumentVersion,
    LlmStatus,
    LlmVerdict,
    RevisionCandidate,
    RevisionScoringConfig,
    RevisionStatus,
    SyncState,
)

KB = "kb-1"


def _v(
    doc_id: str,
    version_no: int = 1,
    *,
    lineage_id: str | None = None,
    status: RevisionStatus = RevisionStatus.ACTIVE,
    kb_id: str = KB,
) -> DocumentVersion:
    return DocumentVersion(
        document_id=doc_id,
        kb_id=kb_id,
        filename=f"{doc_id}.pdf",
        lineage_id=lineage_id,
        version_no=version_no,
        version_label=None,
        effective_date=None,
        revision_status=status,
        sync_state=SyncState.SYNCED,
        file_hash=None,
        superseded_by=None,
        superseded_at=None,
        revised_by=None,
        created_at=datetime(2026, 1, 1),
    )


def _c(doc_id: str, fname: float, content: float, llm: LlmVerdict | None = None) -> RevisionCandidate:
    cfg = RevisionScoringConfig()
    return RevisionCandidate(
        document_id=doc_id,
        filename=f"{doc_id}.pdf",
        version_no=1,
        version_label=None,
        filename_score=fname,
        content_score=content,
        combined_score=RevisionPolicy.combined_score(fname, content, cfg),
        llm_verdict=llm,
        llm_reason=None,
    )


class TestDocumentVersion:
    def test_lineage_defaults_to_own_document_id(self) -> None:
        assert _v("d1").effective_lineage_id == "d1"

    def test_explicit_lineage(self) -> None:
        assert _v("d2", 2, lineage_id="d1").effective_lineage_id == "d1"


class TestSupersedeTarget:
    def test_valid_latest_active_target(self) -> None:
        target = _v("d1")
        RevisionPolicy.validate_supersede_target(target, KB, [target])

    def test_missing_target(self) -> None:
        with pytest.raises(RevisionTargetInvalidError) as e:
            RevisionPolicy.validate_supersede_target(None, KB, [])
        assert e.value.reason == "not_found"

    def test_other_kb(self) -> None:
        target = _v("d1", kb_id="kb-2")
        with pytest.raises(RevisionTargetInvalidError) as e:
            RevisionPolicy.validate_supersede_target(target, KB, [target])
        assert e.value.reason == "other_kb"

    def test_superseded_target(self) -> None:
        old = _v("d1", status=RevisionStatus.SUPERSEDED)
        new = _v("d2", 2, lineage_id="d1")
        with pytest.raises(RevisionTargetInvalidError) as e:
            RevisionPolicy.validate_supersede_target(old, KB, [old, new])
        assert e.value.reason == "not_active"

    def test_not_latest_even_if_active(self) -> None:
        # 되돌리기 중 일시 상태 등 — 계보 최신이 아니면 대체 불가
        old = _v("d1")
        new = _v("d2", 2, lineage_id="d1")
        with pytest.raises(RevisionTargetInvalidError) as e:
            RevisionPolicy.validate_supersede_target(old, KB, [old, new])
        assert e.value.reason == "not_latest"


class TestVersionNumbers:
    def test_next_version_no(self) -> None:
        assert RevisionPolicy.next_version_no([_v("d1"), _v("d2", 2, lineage_id="d1")]) == 3

    def test_next_version_no_empty(self) -> None:
        assert RevisionPolicy.next_version_no([]) == 1

    def test_previous_version_skips_gaps(self) -> None:
        v1 = _v("d1", 1)
        v3 = _v("d3", 3, lineage_id="d1")  # v2 삭제됨
        assert RevisionPolicy.previous_version(v3, [v1, v3]) == v1

    def test_previous_version_none_for_first(self) -> None:
        v1 = _v("d1")
        assert RevisionPolicy.previous_version(v1, [v1]) is None


class TestRollback:
    def test_allowed_returns_previous(self) -> None:
        v1 = _v("d1", status=RevisionStatus.SUPERSEDED)
        v2 = _v("d2", 2, lineage_id="d1")
        assert RevisionPolicy.validate_rollback(v2, [v1, v2]) == v1

    def test_first_version_not_allowed(self) -> None:
        v1 = _v("d1")
        with pytest.raises(RollbackNotAllowedError) as e:
            RevisionPolicy.validate_rollback(v1, [v1])
        assert e.value.reason == "first_version"

    def test_inactive_not_allowed(self) -> None:
        v1 = _v("d1")
        v2 = _v("d2", 2, lineage_id="d1", status=RevisionStatus.SUPERSEDED)
        with pytest.raises(RollbackNotAllowedError) as e:
            RevisionPolicy.validate_rollback(v2, [v1, v2])
        assert e.value.reason == "not_active"

    def test_no_previous_not_allowed(self) -> None:
        v2 = _v("d2", 2, lineage_id="d1")  # v1 삭제됨
        with pytest.raises(RollbackNotAllowedError) as e:
            RevisionPolicy.validate_rollback(v2, [v2])
        assert e.value.reason == "no_previous"


class TestLink:
    def test_valid_link(self) -> None:
        new, old = _v("n1"), _v("o1")
        RevisionPolicy.validate_link(new, old, KB, [new], [old])

    @pytest.mark.parametrize(
        ("new", "old", "reason"),
        [
            (None, _v("o1"), "not_found"),
            (_v("n1"), None, "not_found"),
            (_v("n1", kb_id="kb-2"), _v("o1"), "other_kb"),
            (_v("n1"), _v("o1", kb_id="kb-2"), "other_kb"),
            (_v("n1", status=RevisionStatus.SUPERSEDED), _v("o1"), "not_active"),
            (_v("n1"), _v("o1", status=RevisionStatus.SUPERSEDED), "not_active"),
            (_v("same"), _v("same"), "same_document"),
        ],
    )
    def test_invalid_basic(self, new, old, reason) -> None:
        with pytest.raises(RevisionLinkInvalidError) as e:
            RevisionPolicy.validate_link(
                new, old, KB, [new] if new else [], [old] if old else []
            )
        assert e.value.reason == reason

    def test_source_with_history_rejected(self) -> None:
        new = _v("n2", 2, lineage_id="n1")
        old = _v("o1")
        with pytest.raises(RevisionLinkInvalidError) as e:
            RevisionPolicy.validate_link(new, old, KB, [_v("n1", status=RevisionStatus.SUPERSEDED), new], [old])
        assert e.value.reason == "source_has_history"

    def test_target_not_latest_rejected(self) -> None:
        new = _v("n1")
        old = _v("o1")
        newer = _v("o2", 2, lineage_id="o1")
        with pytest.raises(RevisionLinkInvalidError) as e:
            RevisionPolicy.validate_link(new, old, KB, [new], [old, newer])
        assert e.value.reason == "target_not_latest"


class TestScoring:
    def test_combined_score_weights(self) -> None:
        cfg = RevisionScoringConfig(weight_filename=0.4, weight_content=0.6)
        assert RevisionPolicy.combined_score(1.0, 0.5, cfg) == pytest.approx(0.7)

    def test_select_candidates_union_threshold_and_top_n(self) -> None:
        cfg = RevisionScoringConfig(filename_min=0.6, content_min=0.75, top_n=2)
        fname = {"a": 1.0, "b": 0.3, "c": 0.65, "d": 0.1}
        content = {"b": 0.9, "c": 0.2, "d": 0.5}
        picked = RevisionPolicy.select_candidates(fname, content, cfg)
        # a: 0.4, b: 0.66, c: 0.38, d 제외(어느 기준도 못 넘음)
        assert [p[0] for p in picked] == ["b", "a"]
        assert picked[0][1:] == (0.3, 0.9)

    def test_select_candidates_missing_signal_is_zero(self) -> None:
        cfg = RevisionScoringConfig()
        picked = RevisionPolicy.select_candidates({"a": 1.0}, {}, cfg)
        assert picked == [("a", 1.0, 0.0)]


class TestVerdict:
    cfg = RevisionScoringConfig(suggest_min_combined=0.8)

    def test_llm_same_wins_with_highest_combined(self) -> None:
        cands = [
            _c("x", 1.0, 1.0, LlmVerdict.DIFFERENT),
            _c("y", 0.6, 0.8, LlmVerdict.SAME),
            _c("z", 0.6, 0.7, LlmVerdict.SAME),
        ]
        assert RevisionPolicy.decide_verdict(cands, LlmStatus.OK, self.cfg) == (
            CheckVerdict.REVISION_CANDIDATE,
            "y",
        )

    def test_llm_all_different_is_new(self) -> None:
        cands = [_c("x", 1.0, 1.0, LlmVerdict.DIFFERENT)]
        assert RevisionPolicy.decide_verdict(cands, LlmStatus.OK, self.cfg) == (
            CheckVerdict.NEW,
            None,
        )

    def test_llm_failed_falls_back_to_score(self) -> None:
        cands = [_c("x", 1.0, 0.8)]  # combined 0.88
        assert RevisionPolicy.decide_verdict(cands, LlmStatus.FAILED, self.cfg) == (
            CheckVerdict.REVISION_CANDIDATE,
            "x",
        )

    def test_llm_failed_below_threshold_is_new(self) -> None:
        cands = [_c("x", 0.6, 0.5)]
        assert RevisionPolicy.decide_verdict(cands, LlmStatus.FAILED, self.cfg) == (
            CheckVerdict.NEW,
            None,
        )

    def test_llm_skipped_also_falls_back_to_score(self) -> None:
        cands = [_c("x", 1.0, 0.8)]
        assert RevisionPolicy.decide_verdict(cands, LlmStatus.SKIPPED, self.cfg)[0] is (
            CheckVerdict.REVISION_CANDIDATE
        )

    def test_no_candidates_is_new(self) -> None:
        assert RevisionPolicy.decide_verdict([], LlmStatus.SKIPPED, self.cfg) == (
            CheckVerdict.NEW,
            None,
        )
