"""RevisionCheckUseCase — 사전 점검 (document-revision Design §2.2, §4.2 #1, §10.5).

상태를 바꾸지 않고 판정 로그 1행만 남긴다. LLM·임베딩 실패는 점검을 막지 않는다 (SC-7).
"""
import asyncio
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.document_revision.revision_check_use_case import (
    RevisionCheckUseCase,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.document_revision.value_objects import (
    CheckSource,
    CheckVerdict,
    DocumentVersion,
    JudgeOutcome,
    LlmStatus,
    LlmVerdict,
    RevisionScoringConfig,
    RevisionStatus,
    SyncState,
)
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy

KB_ID = "kb-1"
FILE = b"%PDF new"
HASH = hashlib.sha256(FILE).hexdigest()
HEAD = "제1조(목적) 이 기준은 여신 심사의 기준을 정한다. " * 20


def _user(uid: int = 7) -> User:
    return User(
        email="a@b.c", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED, id=uid,
    )


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID, name="규정", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="col",
    )


def _v(doc_id, filename, version=1, status=RevisionStatus.ACTIVE):
    return DocumentVersion(
        document_id=doc_id, kb_id=KB_ID, filename=filename, lineage_id=None,
        version_no=version, version_label=None, effective_date=None,
        revision_status=status, sync_state=SyncState.SYNCED, file_hash=None,
        superseded_by=None, superseded_at=None, revised_by=None, created_at=None,
    )


class _Deps:
    def __init__(self) -> None:
        self.kb_repo = AsyncMock()
        self.kb_repo.find_by_id.return_value = _kb()
        self.dept_repo = AsyncMock()
        self.dept_repo.find_departments_by_user.return_value = []
        self.parser = MagicMock()
        self.parser.parse_bytes.return_value = [SimpleNamespace(page_content=HEAD)]
        self.revision_repo = AsyncMock()
        self.revision_repo.find_by_hash.return_value = []
        self.revision_repo.find_active_by_kb.return_value = [
            _v("old", "여신심사기준_2025.pdf", 2),
            _v("other", "대출금리표.xlsx"),
        ]
        self.check_log = AsyncMock()
        self.similarity = AsyncMock()
        self.similarity.search.return_value = {"old": 0.9, "other": 0.3}
        self.head_reader = AsyncMock()
        self.head_reader.read.return_value = "구버전 앞부분"
        self.judge = AsyncMock()
        self.judge.judge.return_value = JudgeOutcome(
            verdict=LlmVerdict.SAME, reason="제1조 문구 동일", confidence=0.9
        )
        self.cfg = RevisionScoringConfig(llm_timeout_s=0.2)

    def use_case(self) -> RevisionCheckUseCase:
        return RevisionCheckUseCase(
            kb_repo=self.kb_repo, policy=KnowledgeBasePolicy(),
            dept_repo=self.dept_repo, parser=self.parser,
            revision_repo=self.revision_repo, check_log_repo=self.check_log,
            similarity=self.similarity, head_reader=self.head_reader,
            judge=self.judge, config=self.cfg, logger=MagicMock(),
            id_factory=lambda: "chk-1",
        )


@pytest.fixture
def d() -> _Deps:
    return _Deps()


async def _run(d: _Deps, filename="여신심사기준_2026.pdf", user=None):
    return await d.use_case().execute(KB_ID, user or _user(), FILE, filename, "r")


class TestGuards:
    async def test_kb_not_found(self, d) -> None:
        d.kb_repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await _run(d)

    async def test_no_write_permission(self, d) -> None:
        with pytest.raises(PermissionError):
            await _run(d, user=_user(99))
        d.parser.parse_bytes.assert_not_called()


class TestDuplicate:
    async def test_duplicate_returns_without_parsing(self, d) -> None:
        dup = _v("old", "여신심사기준_2025.pdf", 2)
        d.revision_repo.find_by_hash.return_value = [dup]
        result = await _run(d)
        assert result.verdict is CheckVerdict.DUPLICATE
        assert result.duplicate_of == dup
        assert result.candidates == []
        d.parser.parse_bytes.assert_not_called()
        d.revision_repo.find_by_hash.assert_awaited_once_with(KB_ID, HASH, "r")
        entry = d.check_log.save.call_args.args[0]
        assert entry.verdict == "duplicate" and entry.file_hash == HASH


class TestCandidates:
    async def test_revision_candidate_with_llm_same(self, d) -> None:
        result = await _run(d)
        assert result.check_id == "chk-1"
        assert result.verdict is CheckVerdict.REVISION_CANDIDATE
        assert result.suggested_document_id == "old"
        assert result.llm_status is LlmStatus.OK
        top = result.candidates[0]
        assert top.document_id == "old"
        assert top.filename_score == 1.0 and top.content_score == 0.9
        assert top.combined_score == pytest.approx(0.94)
        assert top.llm_verdict is LlmVerdict.SAME
        assert top.llm_reason == "제1조 문구 동일"
        # 무관 문서는 어느 기준도 못 넘어 후보에서 빠진다
        assert [c.document_id for c in result.candidates] == ["old"]

    async def test_similarity_receives_head_text_within_limit(self, d) -> None:
        d.cfg = RevisionScoringConfig(head_chars=100)
        await _run(d)
        kwargs = d.similarity.search.call_args.kwargs
        assert kwargs["collection_name"] == "col" and kwargs["kb_id"] == KB_ID
        assert len(kwargs["head_text"]) == 100

    async def test_judge_gets_both_heads(self, d) -> None:
        await _run(d)
        kwargs = d.judge.judge.call_args.kwargs
        assert kwargs["new_filename"] == "여신심사기준_2026.pdf"
        assert kwargs["candidate_filename"] == "여신심사기준_2025.pdf"
        assert kwargs["candidate_head"] == "구버전 앞부분"
        assert kwargs["new_head"] == HEAD[:1500]

    async def test_llm_different_means_new_but_candidates_kept(self, d) -> None:
        d.judge.judge.return_value = JudgeOutcome(
            verdict=LlmVerdict.DIFFERENT, reason="다른 규정", confidence=0.8
        )
        result = await _run(d)
        assert result.verdict is CheckVerdict.NEW
        assert result.suggested_document_id is None
        assert result.candidates[0].document_id == "old"

    async def test_no_candidates_skips_llm(self, d) -> None:
        d.similarity.search.return_value = {}
        result = await _run(d, filename="전혀다른문서.pdf")
        assert result.verdict is CheckVerdict.NEW
        assert result.candidates == [] and result.llm_status is LlmStatus.SKIPPED
        d.judge.judge.assert_not_awaited()

    async def test_only_active_documents_are_candidates(self, d) -> None:
        d.similarity.search.return_value = {"old": 0.9, "ghost": 0.99}
        result = await _run(d)
        assert "ghost" not in [c.document_id for c in result.candidates]

    async def test_llm_top_m_limits_judge_calls(self, d) -> None:
        d.revision_repo.find_active_by_kb.return_value = [
            _v(f"d{i}", f"여신심사기준_{i}.pdf") for i in range(5)
        ]
        d.similarity.search.return_value = {f"d{i}": 0.9 - i * 0.01 for i in range(5)}
        d.cfg = RevisionScoringConfig(top_n=3, llm_top_m=2)
        result = await _run(d)
        assert len(result.candidates) == 3
        assert d.judge.judge.await_count == 2
        assert result.candidates[2].llm_verdict is None


class TestFailures:
    async def test_llm_exception_falls_back_to_score(self, d) -> None:
        d.judge.judge.side_effect = RuntimeError("llm down")
        result = await _run(d)
        assert result.llm_status is LlmStatus.FAILED
        assert result.verdict is CheckVerdict.REVISION_CANDIDATE  # 0.94 ≥ 0.8
        assert result.candidates[0].llm_verdict is None

    async def test_llm_timeout_is_failed(self, d) -> None:
        async def _slow(**_):
            await asyncio.sleep(1)

        d.judge.judge.side_effect = _slow
        result = await _run(d)
        assert result.llm_status is LlmStatus.FAILED

    async def test_llm_not_configured_is_skipped(self, d) -> None:
        d.judge.judge.return_value = None
        result = await _run(d)
        assert result.llm_status is LlmStatus.SKIPPED
        assert result.verdict is CheckVerdict.REVISION_CANDIDATE

    async def test_similarity_failure_uses_filename_only(self, d) -> None:
        d.similarity.search.side_effect = RuntimeError("embedding down")
        result = await _run(d)
        assert result.candidates[0].document_id == "old"
        assert result.candidates[0].content_score == 0.0

    async def test_log_save_failure_still_returns(self, d) -> None:
        d.check_log.save.side_effect = RuntimeError("db")
        result = await _run(d)
        assert result.check_id == "chk-1"


class TestLog:
    async def test_log_entry_fields(self, d) -> None:
        result = await _run(d)
        entry = d.check_log.save.call_args.args[0]
        assert entry.check_id == "chk-1" and entry.kb_id == KB_ID
        assert entry.user_id == "7" and entry.source is CheckSource.PRECHECK
        assert entry.normalized_name == "여신심사기준"
        assert entry.verdict == "revision_candidate"
        assert entry.suggested_document_id == "old"
        assert entry.candidates == result.candidates
        assert entry.llm_status is LlmStatus.OK
        assert entry.elapsed_ms >= entry.parse_ms >= 0
        assert entry.decision is None


class TestParseFailure:
    """Act-1 (Gap I3): 파싱 실패는 500 이 아니라 파일명 신호만으로 계속한다."""

    async def test_parse_error_continues_with_filename_only(self, d) -> None:
        d.parser.parse_bytes.side_effect = RuntimeError("broken pdf")
        result = await _run(d)
        assert result.candidates[0].document_id == "old"
        assert result.candidates[0].content_score == 0.0
        d.similarity.search.assert_not_awaited()

    async def test_unsupported_extension_still_raises(self, d) -> None:
        from src.domain.parser.exceptions import UnsupportedFileFormatError

        d.parser.parse_bytes.side_effect = UnsupportedFileFormatError(".docx")
        with pytest.raises(UnsupportedFileFormatError):
            await _run(d, filename="규정.docx")


def test_default_content_threshold_is_calibrated() -> None:
    """Act-1 (Gap C1): 합성 평가에서 개정 쌍 0.65~0.70, 무관 0.31~0.35 → 0.5."""
    assert RevisionScoringConfig().content_min == 0.5
