"""document_extractor_router 테스트 (Design §3-1 에러 계약)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.document_extractor_router import (
    get_document_attachment_store,
    get_extract_document_use_case,
    get_refine_slots_use_case,
    router,
)
from src.application.document_extractor.schemas import (
    ExtractResponse,
    RefineResponse,
    TemplateSlotDto,
)
from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.document_extractor.exceptions import (
    DocumentTooLargeError,
    InvalidDocumentError,
    McpConversionError,
    McpToolNotConfiguredError,
    RegenLimitExceededError,
    SlotExtractionFailedError,
)
from src.interfaces.dependencies.auth import get_current_user


def _user(uid: int = 7) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=uid,
    )


def _make_app(extract_uc=None, refine_uc=None, store=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    if extract_uc is not None:
        app.dependency_overrides[get_extract_document_use_case] = lambda: extract_uc
    if refine_uc is not None:
        app.dependency_overrides[get_refine_slots_use_case] = lambda: refine_uc
    if store is not None:
        app.dependency_overrides[get_document_attachment_store] = lambda: store
    return app


def _extract_response() -> ExtractResponse:
    return ExtractResponse(
        source_file_id="a" * 32,
        source_format="pdf",
        html="<p>양식 {{loan_amount}}</p>",
        suggested_slots=[
            TemplateSlotDto(key="loan_amount", label="여신금액", slot_type="value")
        ],
        mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d",
    )


def _pdf_files():
    return {"file": ("심의서.pdf", b"%PDF-fake", "application/pdf")}


class TestExtract:
    def test_success_200(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_extract_response())
        client = TestClient(_make_app(extract_uc=uc))
        res = client.post("/api/v1/document-extractor/extract", files=_pdf_files())
        assert res.status_code == 200
        body = res.json()
        assert body["source_format"] == "pdf"
        assert body["suggested_slots"][0]["key"] == "loan_amount"
        # owner는 토큰 user.id에서 (위변조 방지)
        assert uc.execute.call_args.kwargs["owner_user_id"] == "7"

    def test_optional_mcp_ids_forwarded(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_extract_response())
        client = TestClient(_make_app(extract_uc=uc))
        client.post(
            "/api/v1/document-extractor/extract",
            files=_pdf_files(),
            data={"mcp_pdf_to_html_tool_id": "mcp_x"},
        )
        kwargs = uc.execute.call_args.kwargs
        assert kwargs["mcp_pdf_to_html_tool_id"] == "mcp_x"
        assert kwargs["mcp_html_to_doc_tool_id"] is None

    @pytest.mark.parametrize(
        "error,status,code",
        [
            (InvalidDocumentError("bad"), 400, "INVALID_DOCUMENT"),
            (DocumentTooLargeError("big"), 413, "DOCUMENT_TOO_LARGE"),
            (McpToolNotConfiguredError("no tool"), 400, "MCP_TOOL_NOT_CONFIGURED"),
            (McpConversionError("fail"), 502, "MCP_CONVERSION_FAILED"),
            (SlotExtractionFailedError("fail"), 502, "SLOT_EXTRACTION_FAILED"),
        ],
    )
    def test_error_contract(self, error, status, code):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=error)
        client = TestClient(_make_app(extract_uc=uc))
        res = client.post("/api/v1/document-extractor/extract", files=_pdf_files())
        assert res.status_code == status
        assert res.json()["detail"]["code"] == code


class TestRefine:
    def test_success_200(self):
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=RefineResponse(
                suggested_slots=[
                    TemplateSlotDto(key="new_key", label="새것", slot_type="value")
                ]
            )
        )
        client = TestClient(_make_app(refine_uc=uc))
        res = client.post(
            "/api/v1/document-extractor/refine",
            json={
                "html": "<p>양식</p>", "instruction": "나눠줘",
                "prev_slots": [], "regen_count": 2,
            },
        )
        assert res.status_code == 200
        assert res.json()["suggested_slots"][0]["key"] == "new_key"

    def test_regen_limit_429(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=RegenLimitExceededError("limit"))
        client = TestClient(_make_app(refine_uc=uc))
        res = client.post(
            "/api/v1/document-extractor/refine",
            json={"html": "x", "instruction": "y", "regen_count": 99},
        )
        assert res.status_code == 429
        assert res.json()["detail"]["code"] == "REGEN_LIMIT_EXCEEDED"


class TestFileDownload:
    def _stored(self, tmp_path, owner="7"):
        path = tmp_path / "out.pdf"
        path.write_bytes(b"%PDF-fake-output")
        return StoredAttachment(
            file_id="b" * 32, type=AttachmentType.DOCUMENT,
            filename="심의서_완성.pdf", size=16, owner_user_id=owner,
            file_path=str(path),
        )

    def test_owner_downloads_200(self, tmp_path):
        store = MagicMock()
        store.load.return_value = self._stored(tmp_path)
        client = TestClient(_make_app(store=store))
        res = client.get(f"/api/v1/document-extractor/files/{'b' * 32}")
        assert res.status_code == 200
        assert res.content == b"%PDF-fake-output"

    def test_not_found_404(self):
        store = MagicMock()
        store.load.return_value = None
        client = TestClient(_make_app(store=store))
        res = client.get(f"/api/v1/document-extractor/files/{'c' * 32}")
        assert res.status_code == 404

    def test_other_owner_403(self, tmp_path):
        store = MagicMock()
        store.load.return_value = self._stored(tmp_path, owner="999")
        client = TestClient(_make_app(store=store))
        res = client.get(f"/api/v1/document-extractor/files/{'b' * 32}")
        assert res.status_code == 403
