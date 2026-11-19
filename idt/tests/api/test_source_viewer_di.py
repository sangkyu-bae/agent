"""source-passage-viewer module-4 — 조립·킬스위치 (Design §6 조립 행, §8.2 #14).

- enabled=False → 부품 None, 라우트 없음(404)
- enabled=True, 경로 없음 → enricher 만(텍스트 뷰어), sink/store 없음
- enabled=True, 경로 있음 → sink·enricher·store 모두
- 조립 실패 → None + warning (앱 기동은 계속)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import source_viewer_di as di


def _settings(enabled=True, storage_dir=""):
    return SimpleNamespace(
        source_viewer_enabled=enabled, document_original_storage_dir=storage_dir,
    )


def test_disabled_builds_nothing():
    assert di.build_source_viewer(_settings(enabled=False), MagicMock()) is None


def test_enabled_without_storage_is_text_only():
    parts = di.build_source_viewer(_settings(), MagicMock())
    assert parts.enricher is not None
    assert parts.sink is None and parts.store is None


def test_enabled_with_storage_builds_all(tmp_path):
    parts = di.build_source_viewer(_settings(storage_dir=str(tmp_path / "orig")), MagicMock())
    assert parts.sink is not None and parts.store is not None
    assert (tmp_path / "orig").is_dir()


def test_assembly_failure_returns_none_and_warns(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")  # 파일 아래에 디렉터리를 만들 수 없다
    logger = MagicMock()
    assert di.build_source_viewer(_settings(storage_dir=str(blocker / "sub")), logger) is None
    logger.warning.assert_called_once()


def test_accessors_return_none_when_disabled(monkeypatch):
    monkeypatch.setattr(di, "_parts", None)
    monkeypatch.setattr(di, "_built", True)
    assert di.source_viewer_sink() is None
    assert di.source_viewer_enricher() is None


def _routes(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def test_wire_without_parts_registers_no_route(monkeypatch):
    monkeypatch.setattr(di, "_parts", None)
    monkeypatch.setattr(di, "_built", True)
    app = FastAPI()
    assert di.wire_source_viewer(app, kb_uc_factory=MagicMock(), get_session=MagicMock()) is False
    assert not any(p.startswith("/api/v1/source-viewer") for p in _routes(app))
    res = TestClient(app).get(
        "/api/v1/source-viewer/kb/kb-1/documents/8f1c2d3e-0000-4000-8000-000000000001/original"
    )
    assert res.status_code == 404


def test_wire_text_only_registers_no_route(monkeypatch):
    monkeypatch.setattr(di, "_parts", di.build_source_viewer(_settings(), MagicMock()))
    monkeypatch.setattr(di, "_built", True)
    app = FastAPI()
    assert di.wire_source_viewer(app, kb_uc_factory=MagicMock(), get_session=MagicMock()) is False
    assert not any(p.startswith("/api/v1/source-viewer") for p in _routes(app))


def test_wire_with_parts_registers_route(monkeypatch, tmp_path):
    parts = di.build_source_viewer(_settings(storage_dir=str(tmp_path)), MagicMock())
    monkeypatch.setattr(di, "_parts", parts)
    monkeypatch.setattr(di, "_built", True)
    app = FastAPI()
    assert di.wire_source_viewer(app, kb_uc_factory=MagicMock(), get_session=MagicMock()) is True
    assert "/api/v1/source-viewer/kb/{kb_id}/documents/{document_id}/original" in _routes(app)
