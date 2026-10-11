"""KB 업로드 경로 HWP 통합 검증 (hwp-parser Design §8.2 I-01).

실제 ExtensionRoutingParser + HwpDocumentParser + 청킹 전략을 UnifiedUploadUseCase에
그대로 넣고, 외부 저장소(Qdrant·ES·임베딩·DB)만 스텁으로 바꾼다.
HWPX는 ZIP+XML이라 메모리에서 정상 파일을 만들 수 있다.
"""
import io
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.application.unified_upload.schemas import UnifiedUploadRequest
from src.application.unified_upload.use_case import UnifiedUploadUseCase
from src.domain.collection.schemas import ActionType, ActivityLogEntry
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.morph.schemas import MorphAnalysisResult, MorphToken
from src.domain.parser.exceptions import HwpParseError
from src.infrastructure.parser.extension_routing_parser import ExtensionRoutingParser
from src.infrastructure.parser.hwp import HwpDocumentParser

_NS = (
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
)


def _p(inner: str) -> str:
    return f"<hp:p><hp:run>{inner}</hp:run></hp:p>"


def _tc(text: str) -> str:
    return f"<hp:tc><hp:subList>{_p(f'<hp:t>{text}</hp:t>')}</hp:subList></hp:tc>"


def _hwpx_bytes() -> bytes:
    table = (
        "<hp:tbl>"
        f"<hp:tr>{_tc('구분')}{_tc('한도')}</hp:tr>"
        f"<hp:tr>{_tc('신용')}{_tc('1억')}</hp:tr>"
        "</hp:tbl>"
    )
    section0 = _p("<hp:t>한도 기준표</hp:t>" + table) + _p("<hp:t>끝.</hp:t>")
    section1 = _p("<hp:t>부칙</hp:t>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        for i, body in enumerate([section0, section1]):
            zf.writestr(f"Contents/section{i}.xml", f"<hs:sec {_NS}>{body}</hs:sec>")
    return buf.getvalue()


def _use_case() -> tuple[UnifiedUploadUseCase, dict]:
    parser = ExtensionRoutingParser(
        pdf_parser=MagicMock(),
        excel_parser=MagicMock(),
        hwp_parser=HwpDocumentParser(max_decompressed_mb=50),
    )
    deps = dict(
        parser=parser,
        collection_repo=AsyncMock(),
        activity_log_repo=AsyncMock(),
        embedding_model_repo=AsyncMock(),
        embedding_factory=MagicMock(),
        qdrant_client=AsyncMock(),
        es_repo=AsyncMock(),
        es_index="test-index",
        morph_analyzer=MagicMock(),
        document_metadata_repo=AsyncMock(),
        activity_log_service=AsyncMock(),
        logger=MagicMock(),
    )
    deps["collection_repo"].collection_exists.return_value = True
    deps["activity_log_repo"].find_all.return_value = [
        ActivityLogEntry(
            id=1,
            collection_name="kb-col",
            action=ActionType.CREATE,
            user_id="admin",
            detail={"embedding_model": "text-embedding-3-small"},
            created_at=datetime.now(),
        )
    ]
    deps["embedding_model_repo"].find_by_model_name.return_value = EmbeddingModel(
        id=1,
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="OpenAI Small",
        vector_dimension=4,
        is_active=True,
        description=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    embedding = AsyncMock()
    embedding.embed_documents.side_effect = lambda texts: [[0.1] * 4 for _ in texts]
    deps["embedding_factory"].create_from_string.return_value = embedding
    deps["morph_analyzer"].analyze.return_value = MorphAnalysisResult(
        tokens=(MorphToken(surface="한도", pos="NNG", start=0, length=2),),
        text="한도",
    )
    deps["es_repo"].bulk_index.side_effect = lambda docs, *a, **k: len(docs)
    use_case = UnifiedUploadUseCase(**deps)
    deps["embedding"] = embedding
    return use_case, deps


def _request(file_bytes: bytes, filename: str) -> UnifiedUploadRequest:
    return UnifiedUploadRequest(
        file_bytes=file_bytes,
        filename=filename,
        user_id="user-1",
        collection_name="kb-col",
        child_chunk_size=500,
        child_chunk_overlap=50,
    )


def _vector_store_mock() -> MagicMock:
    store = AsyncMock()
    store.add_documents.side_effect = lambda docs: [
        MagicMock(value=str(i)) for i in range(len(docs))
    ]
    return store


class TestHwpxUploadThroughRealParser:
    @pytest.mark.asyncio
    async def test_hwpx_upload_produces_chunks_with_table_text(self):
        uc, deps = _use_case()
        with patch(
            "src.application.unified_upload.use_case.QdrantVectorStore",
            return_value=_vector_store_mock(),
        ):
            result = await uc.execute(_request(_hwpx_bytes(), "한도표.hwpx"), "req-1")

        assert result.status == "completed"
        assert result.total_pages == 2  # 섹션 2개 = Document 2개
        assert result.chunk_count > 0
        calls = deps["embedding"].embed_documents.call_args_list
        embedded = " ".join(t for call in calls for t in call.args[0])
        assert "구분 | 한도" in embedded
        assert "신용 | 1억" in embedded
        assert "부칙" in embedded

    @pytest.mark.asyncio
    async def test_corrupt_hwp_rejected_as_value_error(self):
        # 422 매핑 대상: ValueError 계열로 올라와야 한다
        uc, _ = _use_case()
        with pytest.raises(HwpParseError):
            await uc.execute(_request(b"not a real hwp", "깨진.hwp"), "req-1")
