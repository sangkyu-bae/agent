"""ExcelGenerator 테스트 (excel-generator-node Design §2.2 데이터 흐름).

핵심 검증:
- raw 경로: 원천 전량 무손실 복사 + LLM에 전체 데이터 미노출 (Plan SC-2)
- llm 경로: 행 상한 절단 + truncated 플래그 (Plan FR-04)
- 실패: 비JSON → ExcelGenerateError, 빈 계획 → NoExcelDataError (Design §6.1)
"""
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.excel_generator.exceptions import (
    ExcelGenerateError,
    NoExcelDataError,
)
from src.domain.excel_generator.policies import MAX_LLM_STRUCTURED_ROWS
from src.infrastructure.agent_attachment.store import AgentAttachmentStore
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter
from src.infrastructure.excel_generator.generator import ExcelGenerator


class _FakeLLM:
    """계획 JSON을 고정 반환하는 LLM. 프롬프트 노출 검증용으로 호출을 기록."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        return SimpleNamespace(content=self.content)

    def prompt_text(self) -> str:
        return "\n".join(m["content"] for m in self.calls[0])


def _generator(tmp_path, excel_parser=None) -> tuple[ExcelGenerator, AgentAttachmentStore]:
    store = AgentAttachmentStore(str(tmp_path / "attachments"))
    gen = ExcelGenerator(
        exporter=PandasExcelExporter(),
        attachment_store=store,
        logger=MagicMock(),
        excel_parser=excel_parser,
    )
    return gen, store


def _raw_source(rows: int = 1000) -> list[dict]:
    """analysis_source 채널 형태 (supervisor_state.py:53) — ExcelData.to_dict 동형."""
    data = [{"이름": f"n{i}", "값": i} for i in range(rows)]
    return [{
        "origin": "analysis_worker", "kind": "raw_source",
        "excel": {
            "file_id": "src-1", "filename": "원본.xlsx",
            "sheets": {
                "Sheet1": {
                    "sheet_name": "Sheet1", "data": data,
                    "columns": ["이름", "값"], "dtypes": {},
                    "row_count": rows, "column_count": 2,
                },
            },
            "metadata": {},
        },
    }]


def _plan(sheets: list[dict], filename: str = "결과.xlsx") -> str:
    return json.dumps({"filename": filename, "sheets": sheets}, ensure_ascii=False)


async def _generate(gen, llm, *, analysis_source=None, attachments=None):
    return await gen.generate(
        llm=llm,
        analysis_source=analysis_source or [],
        attachments=attachments or [],
        evidence_block="[search_worker]\n수집 근거",
        conversation_block="상위 데이터 수집해서 엑셀로 만들어줘",
        owner_user_id="7",
        request_id="req-1",
    )


def _read_sheet(store, file_id: str, sheet_name: str = None) -> pd.DataFrame:
    stored = store.load(file_id)
    return pd.read_excel(
        io.BytesIO(open(stored.file_path, "rb").read()),
        sheet_name=sheet_name or 0,
    )


class TestRawPath:
    @pytest.mark.asyncio
    async def test_raw_sheet_copies_all_rows_without_llm(self, tmp_path):
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "원본 전체"}]))
        result = await _generate(gen, llm, analysis_source=_raw_source(1000))

        assert result.used_raw_source is True
        assert result.total_rows == 1000
        assert result.truncated is False
        df = _read_sheet(store, result.file_id)
        assert len(df) == 1000  # Plan SC-2: 전량 보존
        assert list(df.columns) == ["이름", "값"]

    @pytest.mark.asyncio
    async def test_full_data_not_exposed_to_llm(self, tmp_path):
        # 카탈로그에는 샘플 5행까지만 — 뒷행 데이터는 LLM 프롬프트에 미노출 (Design §2.2)
        gen, _ = _generator(tmp_path)
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "원본"}]))
        await _generate(gen, llm, analysis_source=_raw_source(1000))

        prompt = llm.prompt_text()
        assert "n0" in prompt          # 샘플은 노출
        assert "n999" not in prompt    # 전체 데이터는 미노출
        assert "1000" in prompt        # 행수 요약은 노출


class TestLlmPath:
    @pytest.mark.asyncio
    async def test_llm_sheet_over_cap_truncates(self, tmp_path):
        gen, store = _generator(tmp_path)
        rows = [[f"v{i}"] for i in range(MAX_LLM_STRUCTURED_ROWS + 100)]
        llm = _FakeLLM(_plan([
            {"source": "llm", "sheet_name": "정리", "columns": ["값"], "rows": rows},
        ]))
        result = await _generate(gen, llm)

        assert result.truncated is True
        assert result.total_rows == MAX_LLM_STRUCTURED_ROWS
        df = _read_sheet(store, result.file_id)
        assert len(df) == MAX_LLM_STRUCTURED_ROWS

    @pytest.mark.asyncio
    async def test_mixed_raw_and_llm_sheets(self, tmp_path):
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan([
            {"source": "raw:0", "sheet_name": "원본"},
            {"source": "llm", "sheet_name": "상위 3",
             "columns": ["이름"], "rows": [["n1"], ["n2"], ["n3"]]},
        ]))
        result = await _generate(gen, llm, analysis_source=_raw_source(10))
        assert result.sheet_count == 2
        assert result.total_rows == 13
        df = _read_sheet(store, result.file_id, sheet_name="상위 3")
        assert len(df) == 3

    @pytest.mark.asyncio
    async def test_code_fenced_json_is_parsed(self, tmp_path):
        gen, _ = _generator(tmp_path)
        fenced = "```json\n" + _plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]) + "\n```"
        result = await _generate(gen, _FakeLLM(fenced))
        assert result.sheet_count == 1


class TestAttachmentPath:
    @pytest.mark.asyncio
    async def test_attachment_parsed_when_no_analysis_source(self, tmp_path):
        # P2 (Design §2.2): analysis_source 없음 + 첨부 엑셀 → 파서 경유 카탈로그
        from src.domain.excel.entities.excel_data import ExcelData
        from src.domain.excel.entities.sheet_data import SheetData

        parser = MagicMock()
        parser.parse.return_value = ExcelData(
            file_id="att-1", filename="첨부.xlsx",
            sheets={"목록": SheetData(
                sheet_name="목록",
                data=[{"품목": "사과"}, {"품목": "배"}],
                columns=["품목"],
            )},
            metadata=MagicMock(to_dict=MagicMock(return_value={})),
        )
        gen, store = _generator(tmp_path, excel_parser=parser)
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "첨부 정리"}]))
        result = await _generate(gen, llm, attachments=[
            {"type": "excel", "file_path": "/tmp/a.xlsx", "user_id": "7"},
        ])
        parser.parse.assert_called_once_with("/tmp/a.xlsx", "7")
        assert result.used_raw_source is True
        assert result.total_rows == 2

    @pytest.mark.asyncio
    async def test_parse_failure_skips_source(self, tmp_path):
        # Design §6.1 #5: 파싱 실패 원천은 제외하고 진행
        parser = MagicMock()
        parser.parse.side_effect = ValueError("bad excel")
        gen, _ = _generator(tmp_path, excel_parser=parser)
        llm = _FakeLLM(_plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        result = await _generate(gen, llm, attachments=[
            {"type": "excel", "file_path": "/tmp/bad.xlsx", "user_id": "7"},
        ])
        assert result.sheet_count == 1


class TestFailures:
    @pytest.mark.asyncio
    async def test_non_json_response_raises(self, tmp_path):
        gen, _ = _generator(tmp_path)
        with pytest.raises(ExcelGenerateError):
            await _generate(gen, _FakeLLM("표를 만들 수 없습니다"))

    @pytest.mark.asyncio
    async def test_empty_plan_raises_no_data(self, tmp_path):
        gen, _ = _generator(tmp_path)
        with pytest.raises(NoExcelDataError):
            await _generate(gen, _FakeLLM(_plan([], filename="")))

    @pytest.mark.asyncio
    async def test_invalid_raw_index_raises(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = _FakeLLM(_plan([{"source": "raw:5", "sheet_name": "x"}]))
        with pytest.raises(ExcelGenerateError):
            await _generate(gen, llm)  # 카탈로그 0개인데 raw:5 참조


class TestStorage:
    @pytest.mark.asyncio
    async def test_saved_as_excel_type_with_owner(self, tmp_path):
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        result = await _generate(gen, llm)
        stored = store.load(result.file_id)
        assert stored is not None
        assert stored.type == AttachmentType.EXCEL
        assert stored.owner_user_id == "7"
        assert stored.filename.endswith(".xlsx")

    @pytest.mark.asyncio
    async def test_filename_path_components_stripped(self, tmp_path):
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan(
            [{"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]}],
            filename="../../evil/결과",
        ))
        result = await _generate(gen, llm)
        assert "/" not in result.filename and "\\" not in result.filename
        assert result.filename.endswith(".xlsx")


class TestFailureBoundaries:
    """Act-1 (analysis I-1/I-2/M-1): 모든 인프라 예외는 ExcelGenerateError로 수렴 (Design §6.1)."""

    @pytest.mark.asyncio
    async def test_store_os_error_wrapped(self, tmp_path):
        gen, store = _generator(tmp_path)
        store.save = MagicMock(side_effect=OSError("disk full"))
        llm = _FakeLLM(_plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        with pytest.raises(ExcelGenerateError, match="disk full"):
            await _generate(gen, llm)

    @pytest.mark.asyncio
    async def test_llm_exception_wrapped(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=TimeoutError("llm timeout"))
        with pytest.raises(ExcelGenerateError, match="시트 계획 생성 오류"):
            await _generate(gen, llm)

    @pytest.mark.asyncio
    async def test_filename_without_extension_gets_xlsx(self, tmp_path):
        gen, _ = _generator(tmp_path)
        assert gen._safe_filename("결과") == "결과.xlsx"
        assert gen._safe_filename("결과.xlsx") == "결과.xlsx"
        assert gen._safe_filename("") == "output.xlsx"


# ── excel-generator-spec-ops (Design §8.5) ──────────────────────────────────
class _SeqLLM:
    """호출마다 준비된 응답을 차례로 반환. 재시도 메시지 검증용."""

    def __init__(self, *contents: str) -> None:
        self.contents = list(contents)
        self.calls: list = []
        self.configs: list = []

    async def ainvoke(self, messages, config=None):
        self.calls.append(messages)
        self.configs.append(config)
        return SimpleNamespace(content=self.contents[len(self.calls) - 1])


def _styled_generator(tmp_path):
    from src.infrastructure.excel_export.styled_excel_exporter import (
        StyledExcelExporter,
    )

    store = AgentAttachmentStore(str(tmp_path / "attachments"))
    logger = MagicMock()
    gen = ExcelGenerator(
        exporter=StyledExcelExporter(logger), attachment_store=store, logger=logger,
    )
    return gen, store, logger


class TestSpecOps:
    @pytest.mark.asyncio
    async def test_raw_ops_not_capped(self, tmp_path):  # G1 / Plan SC-1
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan([{
            "source": "raw:0", "sheet_name": "절반",
            "ops": [
                {"op": "filter", "col": "값", "cmp": ">=", "value": 500},
                {"op": "sort", "by": [{"col": "값", "desc": True}]},
            ],
        }]))
        result = await _generate(gen, llm, analysis_source=_raw_source(1000))

        assert len(llm.calls) == 1
        assert result.total_rows == 500 > MAX_LLM_STRUCTURED_ROWS
        assert result.truncated is False
        df = _read_sheet(store, result.file_id)
        assert len(df) == 500
        assert df.iloc[0]["값"] == 999  # 원천 값 그대로, 내림차순

    @pytest.mark.asyncio
    async def test_raw_groupby_sheet(self, tmp_path):
        gen, store = _generator(tmp_path)
        llm = _FakeLLM(_plan([{
            "source": "raw:0", "sheet_name": "합계",
            "ops": [{"op": "groupby", "by": ["이름"],
                     "agg": [{"col": "값", "fn": "sum", "as": "합계"}]},
                    {"op": "top", "n": 3}],
        }]))
        result = await _generate(gen, llm, analysis_source=_raw_source(10))
        df = _read_sheet(store, result.file_id)
        assert list(df.columns) == ["이름", "합계"]
        assert len(df) == 3

    @pytest.mark.asyncio
    async def test_catalog_exposes_dtypes(self, tmp_path):  # G6
        gen, _ = _generator(tmp_path)
        source = _raw_source(3)
        source[0]["excel"]["sheets"]["Sheet1"]["dtypes"] = {"이름": "object", "값": "int64"}
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "원본"}]))
        await _generate(gen, llm, analysis_source=source)
        assert "int64" in llm.prompt_text()

    @pytest.mark.asyncio
    async def test_prompt_mentions_ops_rules(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "원본"}]))
        await _generate(gen, llm, analysis_source=_raw_source(3))
        prompt = llm.prompt_text()
        assert "ops" in prompt and "column_types" in prompt and "groupby" in prompt


class TestPlanRetry:
    @pytest.mark.asyncio
    async def test_invalid_column_then_valid(self, tmp_path):  # G2 / Plan SC-5
        gen, _ = _generator(tmp_path)
        bad = _plan([{"source": "raw:0", "sheet_name": "상위",
                      "ops": [{"op": "sort", "by": [{"col": "없는컬럼"}]}]}])
        good = _plan([{"source": "raw:0", "sheet_name": "상위",
                       "ops": [{"op": "top", "n": 5}]}])
        llm = _SeqLLM(bad, good)
        result = await _generate(gen, llm, analysis_source=_raw_source(20))

        assert len(llm.calls) == 2
        assert result.total_rows == 5
        retry_messages = llm.calls[1]
        assert retry_messages[2]["role"] == "assistant"
        assert "없는컬럼" in retry_messages[-1]["content"]

    @pytest.mark.asyncio
    async def test_non_json_then_valid(self, tmp_path):  # G3
        gen, _ = _generator(tmp_path)
        llm = _SeqLLM("표를 못 만듭니다", _plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        result = await _generate(gen, llm)
        assert len(llm.calls) == 2
        assert result.sheet_count == 1
        assert "JSON" in llm.calls[1][-1]["content"]

    @pytest.mark.asyncio
    async def test_two_failures_raise(self, tmp_path):  # G4
        gen, _ = _generator(tmp_path)
        bad = _plan([{"source": "raw:9", "sheet_name": "x"}])
        llm = _SeqLLM(bad, bad)
        with pytest.raises(ExcelGenerateError, match="raw"):
            await _generate(gen, llm, analysis_source=_raw_source(3))
        assert len(llm.calls) == 2

    @pytest.mark.asyncio
    async def test_empty_plan_not_retried(self, tmp_path):  # G5
        gen, _ = _generator(tmp_path)
        llm = _SeqLLM(_plan([], filename=""), "unused")
        with pytest.raises(NoExcelDataError):
            await _generate(gen, llm)
        assert len(llm.calls) == 1

    @pytest.mark.asyncio
    async def test_retry_logged(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = _SeqLLM("not json", _plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        await _generate(gen, llm)
        warning_messages = [c.args[0] for c in gen._logger.warning.call_args_list]
        assert "ExcelGenerator plan retry" in warning_messages
        done = [c for c in gen._logger.info.call_args_list if c.args[0] == "ExcelGenerator done"]
        assert done[0].kwargs["retried"] is True


class TestColumnTypes:
    @pytest.mark.asyncio
    async def test_column_types_applied(self, tmp_path):  # G7 / Plan SC-3
        from openpyxl import load_workbook

        gen, store, _ = _styled_generator(tmp_path)
        llm = _FakeLLM(_plan([
            {"source": "raw:0", "sheet_name": "원본", "column_types": {"값": "currency"}},
            {"source": "llm", "sheet_name": "요약", "columns": ["금액"],
             "rows": [["1,500원"]], "column_types": {"금액": "currency"}},
        ]))
        result = await _generate(gen, llm, analysis_source=_raw_source(3))
        stored = store.load(result.file_id)
        wb = load_workbook(stored.file_path)
        assert wb["원본"]["B2"].number_format == "#,##0"
        assert wb["원본"].freeze_panes == "A2"
        assert wb["요약"]["A2"].value == 1500

    @pytest.mark.asyncio
    async def test_invalid_column_type_retried(self, tmp_path):
        gen, _, _ = _styled_generator(tmp_path)
        bad = _plan([{"source": "raw:0", "sheet_name": "원본", "column_types": {"값": "money"}}])
        good = _plan([{"source": "raw:0", "sheet_name": "원본"}])
        llm = _SeqLLM(bad, good)
        await _generate(gen, llm, analysis_source=_raw_source(3))
        assert len(llm.calls) == 2


class TestAct1Generator:
    """Check M-5 (analysis §3): ops 실행 실패 경로·로그 필드·재시도 run_name."""

    @pytest.mark.asyncio
    async def test_ops_runtime_failure_is_wrapped_and_logged(self, tmp_path, monkeypatch):
        from src.infrastructure.excel_generator import generator as generator_module

        def _boom(*args, **kwargs):
            raise KeyError("boom")

        monkeypatch.setattr(generator_module, "apply_ops", _boom)
        gen, _ = _generator(tmp_path)
        llm = _FakeLLM(_plan([{"source": "raw:0", "sheet_name": "상위",
                               "ops": [{"op": "top", "n": 1}]}]))
        with pytest.raises(ExcelGenerateError, match="상위.*연산 실패"):
            await _generate(gen, llm, analysis_source=_raw_source(3))
        error_call = gen._logger.error.call_args
        assert error_call.args[0] == "ExcelGenerator ops failed"
        assert error_call.kwargs["request_id"] == "req-1"
        assert isinstance(error_call.kwargs["exception"], KeyError)

    @pytest.mark.asyncio
    async def test_done_log_counts_ops_sheets(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = _FakeLLM(_plan([
            {"source": "raw:0", "sheet_name": "a", "ops": [{"op": "top", "n": 1}]},
            {"source": "raw:0", "sheet_name": "b"},
        ]))
        await _generate(gen, llm, analysis_source=_raw_source(3))
        done = [c for c in gen._logger.info.call_args_list if c.args[0] == "ExcelGenerator done"]
        assert done[0].kwargs["ops_sheet_count"] == 1
        assert done[0].kwargs["retried"] is False

    @pytest.mark.asyncio
    async def test_retry_uses_separate_run_name(self, tmp_path):
        gen, _ = _generator(tmp_path)
        llm = _SeqLLM("not json", _plan([
            {"source": "llm", "sheet_name": "s", "columns": ["a"], "rows": [["v"]]},
        ]))
        await _generate(gen, llm)
        assert [c["run_name"] for c in llm.configs] == [
            "excel_generator_plan", "excel_generator_plan_retry",
        ]


class TestBlockListContent:
    """실 LLM 스모크(Claude Opus 5.5)에서 발견: thinking 상시 모델은 content가 블록 리스트."""

    @pytest.mark.asyncio
    async def test_thinking_and_text_blocks_are_parsed(self, tmp_path):
        gen, _ = _generator(tmp_path)
        plan = _plan([{"source": "raw:0", "sheet_name": "상위", "ops": [{"op": "top", "n": 2}]}])
        llm = MagicMock()
        llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=[
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": plan},
        ]))
        result = await _generate(gen, llm, analysis_source=_raw_source(5))
        assert result.total_rows == 2
