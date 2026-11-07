"""DocumentComposer 테스트 (Design §4-3, D6).

핵심 검증: 토큰 치환 재현성 · HTML escape · GB6 공란+하이라이트 · JSON 계약 재시도.
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.domain.agent_attachment.value_objects import (
    AttachmentType,
    StoredAttachment,
)
from src.domain.document_extractor.exceptions import ComposeError, McpConversionError
from src.domain.document_extractor.schemas import DocumentTemplate, TemplateSlot
from src.domain.document_extractor.tool_config import DocumentExtractorToolConfig
from src.infrastructure.document_extractor.composer import DocumentComposer


class FakeLLM:
    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self.call_count = 0
        self.configs: list[dict | None] = []

    async def ainvoke(self, messages, config=None):
        self.call_count += 1
        self.configs.append(config)
        self.last_messages = messages
        response = MagicMock()
        response.content = self._contents.pop(0)
        return response


class FakeAdapter:
    def __init__(self, error: Exception | None = None):
        self.html_received = None
        self._error = error

    async def to_document(self, html, output_format, mcp_tool_id, request_id):
        if self._error:
            raise self._error
        self.html_received = html
        return b"FILE-BYTES"


class FakeStore:
    def save(self, *, file_bytes, filename, attachment_type, owner_user_id):
        return StoredAttachment(
            file_id="c" * 32, type=attachment_type, filename=filename,
            size=len(file_bytes), owner_user_id=owner_user_id,
            file_path="/tmp/out",
        )


def _template() -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id=str(uuid.uuid4()), agent_id="agent-1",
        worker_id="document_extractor_worker", name="여신심의서",
        html_skeleton="<p>금액: {{loan_amount}}</p><p>소견: {{opinion}}</p>",
        slots=[
            TemplateSlot(key="loan_amount", label="여신금액", slot_type="value"),
            TemplateSlot(key="opinion", label="소견", slot_type="generated"),
        ],
        source_file_ref="ref", source_format="pdf", status="active",
        created_at=now, updated_at=now,
    )


def _config() -> DocumentExtractorToolConfig:
    return DocumentExtractorToolConfig(
        template_id="t-1", mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d", output_format="pdf",
    )


def _composer(adapter=None) -> tuple[DocumentComposer, FakeAdapter]:
    adapter = adapter or FakeAdapter()
    return DocumentComposer(
        conversion_adapter=adapter,
        attachment_store=FakeStore(),
        logger=MagicMock(),
    ), adapter


async def _compose(composer, llm, **kwargs):
    defaults = dict(
        llm=llm, template=_template(), tool_config=_config(),
        evidence_block="[근거] oo문서: 소견 근거 내용",
        conversation_block="여신금액 5억으로 심의서 작성해줘",
        owner_user_id="7", request_id="req",
    )
    defaults.update(kwargs)
    return await composer.compose(**defaults)


class TestCompose:
    @pytest.mark.asyncio
    async def test_happy_path_fills_and_saves_file(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "5억 원", "opinion": "근거 기반 소견"},
            ensure_ascii=False,
        )])
        composer, adapter = _composer()
        result = await _compose(composer, llm)
        assert result.file_id == "c" * 32
        assert result.filename == "여신심의서.pdf"
        assert "5억 원" in adapter.html_received
        assert "{{" not in adapter.html_received     # 토큰 잔류 없음
        assert result.filled_slots == {"여신금액": "5억 원", "소견": "근거 기반 소견"}
        assert result.unfilled_labels == []

    @pytest.mark.asyncio
    async def test_replacement_is_deterministic(self):
        """토큰 치환 재현성: 같은 입력 → 같은 출력 HTML (방식 A)."""
        payload = json.dumps({"loan_amount": "5억", "opinion": "소견"})
        composer1, adapter1 = _composer()
        composer2, adapter2 = _composer()
        await _compose(composer1, FakeLLM([payload]))
        await _compose(composer2, FakeLLM([payload]))
        assert adapter1.html_received == adapter2.html_received

    @pytest.mark.asyncio
    async def test_values_html_escaped(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "<b>5억</b>", "opinion": "소견"}
        )])
        composer, adapter = _composer()
        await _compose(composer, llm)
        assert "<b>5억</b>" not in adapter.html_received
        assert "&lt;b&gt;5억&lt;/b&gt;" in adapter.html_received

    @pytest.mark.asyncio
    async def test_token_injection_stripped(self):
        llm = FakeLLM([json.dumps(
            {"loan_amount": "5억 {{opinion}}", "opinion": "소견"}
        )])
        composer, adapter = _composer()
        await _compose(composer, llm)
        assert "{{opinion}}" not in adapter.html_received

    @pytest.mark.asyncio
    async def test_gb6_null_slot_left_blank_with_highlight(self):
        """GB6: 근거 없는 슬롯(null)은 공란+하이라이트, 추정값 미생성."""
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": None})])
        composer, adapter = _composer()
        result = await _compose(composer, llm)
        assert 'data-unfilled="opinion"' in adapter.html_received
        assert result.unfilled_labels == ["소견"]
        assert "소견" not in result.filled_slots

    @pytest.mark.asyncio
    async def test_missing_key_retries_then_raises(self):
        """모든 슬롯 key 필수 (D6) — 재시도 후 파일 미생성."""
        incomplete = json.dumps({"loan_amount": "5억"})
        llm = FakeLLM([incomplete, incomplete])
        composer, adapter = _composer()
        with pytest.raises(ComposeError):
            await _compose(composer, llm)
        assert llm.call_count == 2
        assert adapter.html_received is None    # 변환 미호출 = 파일 미생성

    @pytest.mark.asyncio
    async def test_parse_failure_retries_then_raises(self):
        llm = FakeLLM(["not json", "still not json"])
        composer, _ = _composer()
        with pytest.raises(ComposeError):
            await _compose(composer, llm)

    @pytest.mark.asyncio
    async def test_code_fence_tolerated(self):
        payload = json.dumps({"loan_amount": "5억", "opinion": "소견"})
        llm = FakeLLM([f"```json\n{payload}\n```"])
        composer, _ = _composer()
        result = await _compose(composer, llm)
        assert result.unfilled_labels == []

    @pytest.mark.asyncio
    async def test_mcp_failure_propagates(self):
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        composer, _ = _composer(adapter=FakeAdapter(error=McpConversionError("down")))
        with pytest.raises(McpConversionError):
            await _compose(composer, llm)

    @pytest.mark.asyncio
    async def test_llm_called_with_trace_config(self):
        """LangSmith 추적: run_name 'compose:{템플릿명}' + request_id/template_id."""
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        composer, _ = _composer()
        await _compose(composer, llm)
        config = llm.configs[0]
        assert config is not None
        assert config["run_name"] == "compose:여신심의서"
        assert "document-extractor" in config["tags"]
        assert config["metadata"]["request_id"] == "req"
        assert config["metadata"]["template_id"]

    @pytest.mark.asyncio
    async def test_docx_output_filename(self):
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        composer, _ = _composer()
        config = DocumentExtractorToolConfig(
            template_id="t-1", mcp_pdf_to_html_tool_id="mcp_p2h",
            mcp_html_to_doc_tool_id="mcp_h2d", output_format="docx",
        )
        result = await _compose(composer, llm, tool_config=config)
        assert result.filename == "여신심의서.docx"


# ── 2026-11-06 피드백: 공란 표식에 라벨 미병기 · 오늘 날짜 주입 · 라벨 묶음 일관성 ──


def _date_template() -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id=str(uuid.uuid4()), agent_id="agent-1",
        worker_id="document_extractor_worker", name="여신심의서",
        html_skeleton=(
            "<p>심의일자: {{d_year}}년 {{d_month}}월 {{d_day}}일</p>"
            "<p>업체명: {{company}}</p>"
        ),
        slots=[
            TemplateSlot(key="d_year", label="심의일자", slot_type="value"),
            TemplateSlot(key="d_month", label="심의일자", slot_type="value"),
            TemplateSlot(key="d_day", label="심의일자", slot_type="value"),
            TemplateSlot(key="company", label="업체명", slot_type="value"),
        ],
        source_file_ref="ref", source_format="docx", status="active",
        created_at=now, updated_at=now,
    )


class TestUnfilledMarkerAndDates:
    @pytest.mark.asyncio
    async def test_unfilled_marker_has_no_label(self):
        """'[미기재] 여신금액'처럼 라벨이 중복 표기되지 않는다."""
        composer, adapter = _composer()
        llm = FakeLLM([json.dumps({"loan_amount": None, "opinion": "소견"})])
        result = await _compose(composer, llm)
        assert "[미기재]" in adapter.html_received
        assert "[미기재] 여신금액" not in adapter.html_received
        assert result.unfilled_labels == ["여신금액"]

    @pytest.mark.asyncio
    async def test_today_date_is_given_to_llm(self):
        """규칙 6: [기준 정보]의 오늘 날짜가 user 메시지에 실린다."""
        from datetime import date

        composer, _ = _composer()
        llm = FakeLLM([json.dumps({"loan_amount": "5억", "opinion": "소견"})])
        await _compose(composer, llm)
        user_msg = llm.last_messages[-1]["content"]
        assert "[기준 정보]" in user_msg
        assert f"오늘 날짜: {date.today().isoformat()}" in user_msg
        assert user_msg.index("[기준 정보]") < user_msg.index("[근거 자료]")

    @pytest.mark.asyncio
    async def test_partial_date_group_is_blanked(self):
        """규칙 7 후처리: 년/일이 비면 월만 채워진 반쪽 날짜가 되지 않는다."""
        composer, adapter = _composer()
        llm = FakeLLM([json.dumps(
            {"d_year": None, "d_month": "11", "d_day": None, "company": "한빛상사"}
        )])
        result = await _compose(composer, llm, template=_date_template())
        assert "11월" not in adapter.html_received.replace("[미기재]월", "")
        assert adapter.html_received.count("[미기재]") == 3
        assert result.filled_slots == {"업체명": "한빛상사"}
        assert result.unfilled_labels == ["심의일자", "심의일자", "심의일자"]

    @pytest.mark.asyncio
    async def test_full_date_group_is_kept(self):
        composer, adapter = _composer()
        llm = FakeLLM([json.dumps(
            {"d_year": "2026", "d_month": "11", "d_day": "06", "company": None}
        )])
        await _compose(composer, llm, template=_date_template())
        assert "2026년 11월 06일" in adapter.html_received
        assert adapter.html_received.count("[미기재]") == 1


class TestSampleValueFormatHint:
    def test_prompt_shows_sample_value_format_for_value_slots(self):
        """규칙 8: 예시값 형식을 보여줘 고정 문구 반복('연연 5.8%')을 막는다."""
        now = datetime.now(timezone.utc)
        template = DocumentTemplate(
            id="t", agent_id="a", worker_id="w", name="여신심의서",
            html_skeleton="<p>연 {{rate}}</p><p>{{opinion}}</p>",
            slots=[
                TemplateSlot(key="rate", label="적용 금리", slot_type="value",
                             sample_value="5.8%"),
                TemplateSlot(key="opinion", label="심사 의견", slot_type="generated",
                             sample_value="긴\n\t서술"),
            ],
            source_file_ref="ref", source_format="docx", status="active",
            created_at=now, updated_at=now,
        )
        prompt = DocumentComposer._build_prompt(template)
        assert "rate (value): 적용 금리 / 예시값 형식: 5.8%" in prompt
        # generated 슬롯은 예시 서술을 보여주지 않는다 (예시 문장 복제 방지)
        assert "긴 서술" not in prompt


# ── docx-format-preserving-fill §8.3 — 원본 DOCX 직접 채움 분기 (C-01~05) ─────────


class FakeFiller:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple] = []

    def fill(self, source_path, slots, values, request_id):
        self.calls.append((source_path, [s.key for s in slots], dict(values)))
        return self.result


def _docx_template() -> DocumentTemplate:
    now = datetime.now(timezone.utc)
    return DocumentTemplate(
        id=str(uuid.uuid4()), agent_id="agent-1",
        worker_id="document_extractor_worker", name="여신심의서",
        html_skeleton="<p>금액: {{loan_amount}}</p><p>소견: {{opinion}}</p>",
        slots=[
            TemplateSlot(key="loan_amount", label="여신금액", slot_type="value"),
            TemplateSlot(key="opinion", label="소견", slot_type="generated"),
        ],
        source_file_ref="uploads/document_templates/t.docx",
        source_format="docx", status="active",
        created_at=now, updated_at=now,
    )


def _docx_config() -> DocumentExtractorToolConfig:
    return DocumentExtractorToolConfig(
        template_id="t-1", mcp_pdf_to_html_tool_id="mcp_p2h",
        mcp_html_to_doc_tool_id="mcp_h2d", output_format="docx",
    )


class _SpyStore(FakeStore):
    def save(self, *, file_bytes, filename, attachment_type, owner_user_id):
        self.saved = file_bytes
        return super().save(file_bytes=file_bytes, filename=filename,
                            attachment_type=attachment_type, owner_user_id=owner_user_id)


def _docx_composer(filler, adapter=None):
    from src.infrastructure.document_extractor.docx_filler import DocxFillResult  # noqa: F401

    adapter = adapter or FakeAdapter()
    store = _SpyStore()
    logger = MagicMock()
    composer = DocumentComposer(
        conversion_adapter=adapter, attachment_store=store, logger=logger,
        docx_filler=filler,
    )
    return composer, adapter, store, logger


_VALUES = json.dumps({"loan_amount": "5억", "opinion": None})


class TestDocxDirectFill:
    @pytest.mark.asyncio
    async def test_docx_template_uses_filler_without_mcp(self):  # C-01
        from src.infrastructure.document_extractor.docx_filler import DocxFillResult

        filler = FakeFiller(DocxFillResult(b"DOCX-DIRECT"))
        composer, adapter, store, logger = _docx_composer(filler)
        result = await _compose(composer, FakeLLM([_VALUES]),
                                template=_docx_template(), tool_config=_docx_config())
        assert adapter.html_received is None  # MCP 변환 미호출
        assert store.saved == b"DOCX-DIRECT"
        assert filler.calls[0][0] == "uploads/document_templates/t.docx"
        assert filler.calls[0][2] == {"loan_amount": "5억", "opinion": None}
        assert result.filename == "여신심의서.docx"
        assert logger.info.call_args.kwargs["path"] == "docx_direct"

    @pytest.mark.asyncio
    async def test_missing_sample_falls_back_to_html(self):  # C-02 / SC-5
        from src.infrastructure.document_extractor.docx_filler import DocxFillResult

        filler = FakeFiller(DocxFillResult(None, ["opinion"], "sample_not_found"))
        composer, adapter, store, logger = _docx_composer(filler)
        await _compose(composer, FakeLLM([_VALUES]),
                       template=_docx_template(), tool_config=_docx_config())
        assert adapter.html_received is not None
        assert store.saved == b"FILE-BYTES"
        warn = logger.warning.call_args
        assert warn.args[0] == "DocumentComposer docx fill fallback"
        assert warn.kwargs["missing_keys"] == ["opinion"]
        assert warn.kwargs["reason"] == "sample_not_found"
        assert logger.info.call_args.kwargs["path"] == "html"

    @pytest.mark.asyncio
    async def test_pdf_template_never_calls_filler(self):  # C-03 / SC-6
        from src.infrastructure.document_extractor.docx_filler import DocxFillResult

        filler = FakeFiller(DocxFillResult(b"X"))
        composer, adapter, _, _ = _docx_composer(filler)
        await _compose(composer, FakeLLM([_VALUES]))  # 기본 템플릿은 pdf
        assert filler.calls == []
        assert adapter.html_received is not None

    @pytest.mark.asyncio
    async def test_docx_source_but_pdf_output_uses_html(self):  # D6
        from src.infrastructure.document_extractor.docx_filler import DocxFillResult

        filler = FakeFiller(DocxFillResult(b"X"))
        composer, adapter, _, _ = _docx_composer(filler)
        await _compose(composer, FakeLLM([_VALUES]),
                       template=_docx_template(), tool_config=_config())
        assert filler.calls == []

    @pytest.mark.asyncio
    async def test_result_contract_same_on_both_paths(self):  # C-05
        from src.infrastructure.document_extractor.docx_filler import DocxFillResult

        direct, *_ = _docx_composer(FakeFiller(DocxFillResult(b"D")))
        fallback, *_ = _docx_composer(FakeFiller(DocxFillResult(None, ["x"], "sample_not_found")))
        a = await _compose(direct, FakeLLM([_VALUES]),
                           template=_docx_template(), tool_config=_docx_config())
        b = await _compose(fallback, FakeLLM([_VALUES]),
                           template=_docx_template(), tool_config=_docx_config())
        assert a.filled_slots == b.filled_slots == {"여신금액": "5억"}
        assert a.unfilled_labels == b.unfilled_labels == ["소견"]
