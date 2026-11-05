"""QuickCreateKnowledgeBaseUseCase — agent-kb-quick-setup Design §4.2 /quick.

FR-04/FR-05.

흡수 지점은 파일 루프 1곳뿐: KB 생성 실패는 전파, 파일 단위 실패는 status=failed.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.knowledge_base.quick_create_use_case import (
    QuickCreateKnowledgeBaseUseCase,
    QuickFile,
)
from src.application.unified_upload.schemas import (
    EsStoreResult,
    QdrantStoreResult,
    UnifiedUploadResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.kb_default_setting.errors import KbDefaultsNotConfiguredError
from src.domain.knowledge_base.entities import KnowledgeBase


def _user() -> User:
    return User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _kb(name: str = "여신 상담봇 지식") -> KnowledgeBase:
    return KnowledgeBase(
        id="3f1a9c2e-aaaa-bbbb-cccc-dddddddddddd",
        name=name,
        owner_id=1,
        scope=CollectionScope.PERSONAL,
        collection_name="kb-3f1a9c2e",
    )


def _upload_result(filename: str, chunks: int = 3, status: str = "completed"):
    return UnifiedUploadResult(
        document_id=f"doc-{filename}",
        filename=filename,
        total_pages=1,
        chunk_count=chunks,
        collection_name="kb-3f1a9c2e",
        qdrant=QdrantStoreResult(stored_ids=["a"], embedding_model="m"),
        es=EsStoreResult(indexed_count=chunks),
        chunking_config={},
        status=status,
    )


@pytest.fixture
def kb_uc() -> AsyncMock:
    uc = AsyncMock()
    uc.create.side_effect = lambda **kw: _kb(kw["name"])
    return uc


@pytest.fixture
def upload_uc() -> AsyncMock:
    uc = AsyncMock()
    uc.execute.side_effect = lambda kb_id, user, data, filename, rid: (
        _upload_result(filename),
        _kb(),
        None,
    )
    return uc


@pytest.fixture
def use_case(kb_uc, upload_uc) -> QuickCreateKnowledgeBaseUseCase:
    return QuickCreateKnowledgeBaseUseCase(
        kb_use_case=kb_uc, upload_use_case=upload_uc, logger=MagicMock()
    )


def _files(*names: str) -> list[QuickFile]:
    return [QuickFile(filename=n, content=b"%PDF-1.4") for n in names]


class TestHappyPath:
    async def test_creates_kb_without_collection_and_uploads_in_order(
        self, use_case, kb_uc, upload_uc
    ):
        result = await use_case.execute(
            user=_user(),
            name="여신 상담봇 지식",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("a.pdf", "b.xlsx"),
            request_id="req",
        )
        create_kwargs = kb_uc.create.await_args.kwargs
        assert create_kwargs["collection_name"] is None
        assert create_kwargs["scope"] == CollectionScope.PERSONAL
        # FR-05: 청킹은 기본 프로파일 — 명시 오버라이드 없음
        assert create_kwargs.get("use_clause_chunking", False) is False
        assert create_kwargs.get("use_custom_chunking", False) is False
        assert [d.filename for d in result.documents] == ["a.pdf", "b.xlsx"]
        assert all(d.status == "uploaded" for d in result.documents)
        assert result.uploaded_count == 2 and result.failed_count == 0
        assert result.kb.collection_name == "kb-3f1a9c2e"
        assert upload_uc.execute.await_count == 2


class TestNameDedup:
    async def test_duplicate_name_gets_suffix(self, use_case, kb_uc):
        calls: list[str] = []

        def _create(**kw):
            calls.append(kw["name"])
            if len(calls) == 1:
                raise ValueError(f"Knowledge base '{kw['name']}' already exists")
            return _kb(kw["name"])

        kb_uc.create.side_effect = _create
        result = await use_case.execute(
            user=_user(),
            name="A 지식",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("a.pdf"),
            request_id="req",
        )
        assert calls == ["A 지식", "A 지식 (2)"]
        assert result.kb.name == "A 지식 (2)"

    async def test_other_create_errors_propagate(self, use_case, kb_uc):
        kb_uc.create.side_effect = KbDefaultsNotConfiguredError()
        with pytest.raises(KbDefaultsNotConfiguredError):
            await use_case.execute(
                user=_user(),
                name="A",
                scope=CollectionScope.PERSONAL,
                department_id=None,
                files=_files("a.pdf"),
                request_id="req",
            )

    async def test_permission_error_propagates(self, use_case, kb_uc, upload_uc):
        kb_uc.create.side_effect = PermissionError("no dept")
        with pytest.raises(PermissionError):
            await use_case.execute(
                user=_user(),
                name="A",
                scope=CollectionScope.DEPARTMENT,
                department_id="d9",
                files=_files("a.pdf"),
                request_id="req",
            )
        upload_uc.execute.assert_not_awaited()


class TestPartialFailure:
    async def test_file_failure_is_recorded_not_raised(self, use_case, upload_uc):
        def _exec(kb_id, user, data, filename, rid):
            if filename == "locked.pdf":
                raise ValueError("암호화된 문서입니다")
            return (_upload_result(filename), _kb(), None)

        upload_uc.execute.side_effect = _exec
        result = await use_case.execute(
            user=_user(),
            name="A",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("ok.pdf", "locked.pdf"),
            request_id="req",
        )
        assert result.uploaded_count == 1 and result.failed_count == 1
        failed = result.documents[1]
        assert failed.status == "failed"
        assert failed.error == "암호화된 문서입니다"
        assert failed.document_id is None and failed.chunk_count == 0

    async def test_unexpected_exception_also_degraded_with_log(
        self, use_case, upload_uc
    ):
        upload_uc.execute.side_effect = RuntimeError("qdrant down")
        logger = MagicMock()
        use_case._logger = logger
        result = await use_case.execute(
            user=_user(),
            name="A",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("a.pdf"),
            request_id="req",
        )
        assert result.failed_count == 1
        assert logger.warning.called
        assert "exception" in logger.warning.call_args.kwargs

    async def test_store_level_failed_status_counts_as_failed(
        self, use_case, upload_uc
    ):
        upload_uc.execute.side_effect = lambda kb_id, user, data, filename, rid: (
            _upload_result(filename, chunks=0, status="failed"),
            _kb(),
            None,
        )
        result = await use_case.execute(
            user=_user(),
            name="A",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("a.pdf"),
            request_id="req",
        )
        assert result.failed_count == 1
        assert result.documents[0].status == "failed"

    async def test_all_failed_still_returns_kb(self, use_case, upload_uc):
        upload_uc.execute.side_effect = ValueError("bad")
        result = await use_case.execute(
            user=_user(),
            name="A",
            scope=CollectionScope.PERSONAL,
            department_id=None,
            files=_files("a.pdf", "b.pdf"),
            request_id="req",
        )
        assert result.kb.id and result.uploaded_count == 0


class TestFileValidation:
    async def test_zero_files_rejected_before_kb_creation(self, use_case, kb_uc):
        with pytest.raises(ValueError):
            await use_case.execute(
                user=_user(), name="A", scope=CollectionScope.PERSONAL,
                department_id=None, files=[], request_id="req",
            )
        kb_uc.create.assert_not_awaited()

    async def test_too_many_files_rejected(self, use_case, kb_uc):
        with pytest.raises(ValueError):
            await use_case.execute(
                user=_user(), name="A", scope=CollectionScope.PERSONAL,
                department_id=None, files=_files(*[f"{i}.pdf" for i in range(11)]),
                request_id="req",
            )
        kb_uc.create.assert_not_awaited()

    async def test_unsupported_extension_rejected(self, use_case, kb_uc):
        with pytest.raises(ValueError, match="exe"):
            await use_case.execute(
                user=_user(), name="A", scope=CollectionScope.PERSONAL,
                department_id=None, files=_files("virus.exe"), request_id="req",
            )
        kb_uc.create.assert_not_awaited()


class TestAbsorptionContract:
    """AST 계약 — 광역 `except Exception` 은 파일 업로드 1곳(_upload_one)뿐이다."""

    def test_single_broad_absorb_site(self):
        src = (
            Path(__file__).resolve().parents[3]
            / "src" / "application" / "knowledge_base" / "quick_create_use_case.py"
        )
        tree = ast.parse(src.read_text(encoding="utf-8"))
        sites: list[str] = []
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.ExceptHandler) and (
                    node.type is None
                    or (isinstance(node.type, ast.Name) and node.type.id == "Exception")
                ):
                    sites.append(fn.name)
        assert sites == ["_upload_one"], sites
