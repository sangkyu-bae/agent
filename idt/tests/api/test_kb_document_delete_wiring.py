"""KB 문서 삭제 DI 배선 — 플레이스홀더만 남으면 운영에서 500이 난다.

세션 공유 계약도 함께 확인한다: 메타·잡 행·활동 로그가 같은 요청 세션을 써야
함께 커밋된다 (kb-document-management Design §1.3).
"""
from unittest.mock import MagicMock, patch

from src.api import main as main_module
from src.api.routes.knowledge_base_router import (
    get_delete_kb_document_use_case,
)


def _build_use_case(session: MagicMock):
    with (
        patch.object(main_module, "AsyncQdrantClient"),
        patch.object(main_module.ElasticsearchClient, "from_config"),
    ):
        factory = main_module.create_kb_document_delete_factory(
            lambda s: MagicMock(session=s)
        )
    return factory(session)


def test_factory_builds_use_case_with_single_request_session():
    session = MagicMock()

    use_case = _build_use_case(session)
    deleter = use_case._deleter

    assert use_case._job_repo._session is session
    assert use_case._guard._repo._session is session
    assert deleter._metadata_repo._session is session
    assert deleter._activity_log_service._repo._session is session


def test_app_overrides_placeholder():
    assert get_delete_kb_document_use_case in main_module.app.dependency_overrides
