"""excel-preview DI 배선 — 실제 create_app() 오버라이드를 검증한다.

회귀: create_app() 시점에 PreviewExcelUseCase 를 미리 만들면 lifespan 이
_attachment_store 를 채우기 전 값(None)이 고정되어 프리뷰가 500
(AttributeError: 'NoneType' object has no attribute 'load') 을 냈다.
라우터 테스트는 유스케이스를 스텁으로 바꿔 이 경로를 실행하지 않는다.
"""
from unittest.mock import MagicMock

import src.api.main as main_module
from src.api.routes.document_extractor_router import get_excel_preview_use_case


def test_preview_use_case_uses_store_assigned_by_lifespan(monkeypatch):
    app = main_module.create_app()
    lifespan_store = MagicMock(name="attachment_store")
    # create_app() 이후 lifespan 이 전역 저장소를 채우는 상황
    monkeypatch.setattr(main_module, "_attachment_store", lifespan_store)

    use_case = app.dependency_overrides[get_excel_preview_use_case]()

    assert use_case._store is lifespan_store
