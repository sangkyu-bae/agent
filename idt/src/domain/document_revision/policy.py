"""RevisionPolicy — 개정 계보 규칙과 후보 판정 규칙 (순수 함수).

Design Ref: document-revision §3.2 — 한 계보의 active 는 최대 1개이며
항상 최대 version_no. 이전 버전은 포인터가 아니라 (계보, version_no < 현재) 중 최대값으로 찾는다.
"""
from __future__ import annotations

from src.domain.document_revision.errors import (
    RevisionLinkInvalidError,
    RevisionTargetInvalidError,
    RollbackNotAllowedError,
)
from src.domain.document_revision.value_objects import (
    CheckVerdict,
    DocumentVersion,
    LlmStatus,
    LlmVerdict,
    RevisionCandidate,
    RevisionScoringConfig,
)


def _latest(versions: list[DocumentVersion]) -> DocumentVersion | None:
    return max(versions, key=lambda v: v.version_no, default=None)


class RevisionPolicy:
    # ── 계보 ──────────────────────────────────────────────
    @staticmethod
    def validate_supersede_target(
        target: DocumentVersion | None,
        kb_id: str,
        lineage_versions: list[DocumentVersion],
    ) -> None:
        """대체 대상: 같은 KB · active · 계보 최신 (Plan FR-09)."""
        if target is None:
            raise RevisionTargetInvalidError("not_found")
        if target.kb_id != kb_id:
            raise RevisionTargetInvalidError("other_kb")
        if not target.is_active:
            raise RevisionTargetInvalidError("not_active")
        latest = _latest(lineage_versions)
        if latest is not None and latest.document_id != target.document_id:
            raise RevisionTargetInvalidError("not_latest")

    @staticmethod
    def next_version_no(lineage_versions: list[DocumentVersion]) -> int:
        latest = _latest(lineage_versions)
        return latest.version_no + 1 if latest else 1

    @staticmethod
    def previous_version(
        current: DocumentVersion, lineage_versions: list[DocumentVersion]
    ) -> DocumentVersion | None:
        older = [v for v in lineage_versions if v.version_no < current.version_no]
        return _latest(older)

    @staticmethod
    def validate_rollback(
        current: DocumentVersion | None, lineage_versions: list[DocumentVersion]
    ) -> DocumentVersion:
        """되돌릴 수 있으면 복귀시킬 이전 버전을 반환한다 (Plan FR-11)."""
        if current is None:
            raise RollbackNotAllowedError("not_found")
        if not current.is_active:
            raise RollbackNotAllowedError("not_active")
        if current.version_no <= 1:
            raise RollbackNotAllowedError("first_version")
        previous = RevisionPolicy.previous_version(current, lineage_versions)
        if previous is None:
            raise RollbackNotAllowedError("no_previous")
        return previous

    @staticmethod
    def validate_link(
        source: DocumentVersion | None,
        target: DocumentVersion | None,
        kb_id: str,
        source_lineage_versions: list[DocumentVersion],
        target_lineage_versions: list[DocumentVersion],
    ) -> None:
        """사후 연결: source(신버전)가 target(구버전)을 대체 (Plan FR-12)."""
        if source is None or target is None:
            raise RevisionLinkInvalidError("not_found")
        if source.kb_id != kb_id or target.kb_id != kb_id:
            raise RevisionLinkInvalidError("other_kb")
        if not source.is_active or not target.is_active:
            raise RevisionLinkInvalidError("not_active")
        if source.document_id == target.document_id:
            raise RevisionLinkInvalidError("same_document")
        if source.lineage_id is not None or len(source_lineage_versions) > 1:
            raise RevisionLinkInvalidError("source_has_history")
        latest = _latest(target_lineage_versions)
        if latest is not None and latest.document_id != target.document_id:
            raise RevisionLinkInvalidError("target_not_latest")

    # ── 후보 판정 ──────────────────────────────────────────
    @staticmethod
    def combined_score(
        filename_score: float, content_score: float, cfg: RevisionScoringConfig
    ) -> float:
        return cfg.weight_filename * filename_score + cfg.weight_content * content_score

    @staticmethod
    def select_candidates(
        filename_scores: dict[str, float],
        content_scores: dict[str, float],
        cfg: RevisionScoringConfig,
    ) -> list[tuple[str, float, float]]:
        """(document_id, filename_score, content_score) 목록.

        두 기준의 합집합을 combined 내림차순으로 top_n 개 고른다.
        """
        picked: list[tuple[str, float, float]] = []
        for doc_id in set(filename_scores) | set(content_scores):
            fname = filename_scores.get(doc_id, 0.0)
            content = content_scores.get(doc_id, 0.0)
            if fname >= cfg.filename_min or content >= cfg.content_min:
                picked.append((doc_id, fname, content))
        picked.sort(
            key=lambda p: (-RevisionPolicy.combined_score(p[1], p[2], cfg), p[0])
        )
        return picked[: cfg.top_n]

    @staticmethod
    def decide_verdict(
        candidates: list[RevisionCandidate],
        llm_status: LlmStatus,
        cfg: RevisionScoringConfig,
    ) -> tuple[CheckVerdict, str | None]:
        """duplicate 는 호출부가 먼저 처리한다 (Design §4.2 verdict 결정 규칙 2~4)."""
        same = [c for c in candidates if c.llm_verdict is LlmVerdict.SAME]
        if same:
            best = max(same, key=lambda c: c.combined_score)
            return CheckVerdict.REVISION_CANDIDATE, best.document_id
        if llm_status is not LlmStatus.OK:
            fallback = [
                c
                for c in candidates
                if c.llm_verdict is not LlmVerdict.DIFFERENT
                and c.combined_score >= cfg.suggest_min_combined
            ]
            if fallback:
                best = max(fallback, key=lambda c: c.combined_score)
                return CheckVerdict.REVISION_CANDIDATE, best.document_id
        return CheckVerdict.NEW, None
