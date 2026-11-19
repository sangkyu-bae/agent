"""ExcelGenerator: 하이브리드 소싱 엑셀 생성기 (excel-generator-node Design §2).

시트 계획 LLM 1회 → raw 무손실 복사 / llm 상한 절단 → PandasExcelExporter 변환
→ AgentAttachmentStore 저장 (DocumentGenerator 동형).

excel-generator-spec-ops: raw 시트 연산 명세(ops)는 pandas 실행기가, 컬럼 의미 타입
(column_types)은 exporter가 처리한다. 계획 파싱·검증 실패 시 위반 사유를 붙여
1회 재요청한다 (Design §6.1).
"""
import json
import re
from pathlib import PurePath

from src.domain.agent_attachment.value_objects import AttachmentType
from src.domain.excel_export.schemas import ExcelExportRequest, ExcelSheetData
from src.domain.excel_generator.exceptions import (
    ExcelGenerateError,
    NoExcelDataError,
)
from src.domain.excel_generator.policies import (
    MAX_LLM_STRUCTURED_ROWS,
    parse_raw_index,
    validate_plan,
)
from src.domain.excel_generator.schemas import (
    ExcelGenerateResult,
    RawSourceRef,
    SheetPlanItem,
)
from src.domain.llm.message_content import coerce_message_text
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.excel_generator.ops_executor import apply_ops

_SAMPLE_ROWS = 5          # 카탈로그에 노출할 원천 샘플 행 수 (Design §2.2)
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_MAX_SHEET_NAME_LEN = 31  # Excel 시트명 하드 리밋
_RETRY_ECHO_MAX_CHARS = 4000  # 재요청 시 되돌려 보내는 1차 응답 길이 상한 (Design §6.2)

_PLAN_GUIDELINES = (
    "너는 엑셀 파일 생성 계획을 세우는 도우미다. 아래 재료로 시트 계획 JSON만 출력하라.\n"
    "규칙:\n"
    '1. 출력은 JSON 하나: {"filename": "<파일명>.xlsx", "sheets": [...]}\n'
    "2. [원천 카탈로그]의 데이터를 담을 시트는 "
    '{"source": "raw:<번호>", "sheet_name": "..."} 로 참조만 하라. '
    "카탈로그 데이터를 직접 옮겨 적지 마라.\n"
    # Design §11.3: 원천 가공은 LLM 재작성이 아니라 ops 명세로 (Plan FR-10)
    "3. 원천 데이터의 일부만·정렬·상위 N·집계가 필요하면 "
    'raw 시트에 "ops" 배열을 붙여라. '
    "ops는 적힌 순서대로 실행되고 여러 filter는 AND다.\n"
    '   - {"op": "select", "columns": [...]}\n'
    '   - {"op": "filter", "col": "...", '
    '"cmp": "== | != | > | >= | < | <= | contains | in", "value": ...}\n'
    '   - {"op": "sort", "by": [{"col": "...", "desc": true}]}\n'
    '   - {"op": "top", "n": 10}\n'
    '   - {"op": "groupby", "by": [...], '
    '"agg": [{"col": "...", "fn": "sum | mean | count | min | max", "as": "..."}]}\n'
    "4. 검색 결과·대화 등 비정형 재료에서 표를 만들 때만 "
    '{"source": "llm", "sheet_name": "...", "columns": [...], "rows": [[...]]} 를 사용하라.\n'
    '5. 컬럼 표시 형식이 필요하면 "column_types": '
    '{"컬럼명": "text | integer | number | currency | percent | date"} 를 붙여라. '
    "percent는 값이 0~1 비율이거나 '8.9%'처럼 %가 붙은 값일 때 쓴다. "
    "컬럼명은 ops 실행 후 결과 컬럼 기준이다. "
    # claude-agent-e2e-fixes Design §4.3: 퍼센트 컬럼 조건은 % 를 붙여야 비율로 비교된다
    "퍼센트 컬럼의 filter 값은 '5%'처럼 %를 붙여라.\n"
    '6. 정리할 데이터가 전혀 없으면 {"filename": "", "sheets": []} 를 출력하라.\n'
    "7. JSON 외 다른 텍스트를 출력하지 마라."
)


class ExcelGenerator:
    """소스 카탈로그 + 누적 컨텍스트 → 시트 계획 → xlsx 변환 → 첨부 저장."""

    def __init__(
        self,
        exporter,
        attachment_store,
        logger: LoggerInterface,
        excel_parser=None,
        llm_input_max_chars: int = 20000,
    ) -> None:
        self._exporter = exporter
        self._store = attachment_store
        self._logger = logger
        # P2 (Design §2.2): 첨부 엑셀 직접 파싱용 — 미주입 시 첨부 경로 비활성.
        self._excel_parser = excel_parser
        self._input_max_chars = llm_input_max_chars

    async def generate(
        self,
        llm,
        *,
        analysis_source: list[dict],
        attachments: list[dict],
        evidence_block: str,
        conversation_block: str,
        owner_user_id: str,
        request_id: str,
        worker_context_block: str = "",
    ) -> ExcelGenerateResult:
        catalog, sheet_store = self._build_catalog(
            analysis_source, attachments, owner_user_id, request_id
        )
        filename, items, retried = await self._plan_sheets(
            llm, catalog, sheet_store, evidence_block, conversation_block,
            request_id, worker_context_block,
        )
        if not items:
            raise NoExcelDataError("엑셀로 정리할 데이터가 없습니다")

        sheets, truncated, used_raw = self._materialize(
            items, sheet_store, request_id
        )
        stored = self._export_and_save(
            filename, sheets, owner_user_id, request_id
        )
        result = ExcelGenerateResult(
            file_id=stored.file_id,
            filename=stored.filename,
            sheet_count=len(sheets),
            total_rows=sum(len(s.rows) for s in sheets),
            truncated=truncated,
            used_raw_source=used_raw,
            empty_columns=_empty_columns(sheets),
        )
        self._log_done(result, request_id, retried, items)
        return result

    def _log_done(self, result, request_id: str, retried: bool, items) -> None:
        self._logger.info(
            "ExcelGenerator done",
            request_id=request_id,
            file_id=result.file_id,
            sheet_count=result.sheet_count,
            total_rows=result.total_rows,
            truncated=result.truncated,
            retried=retried,  # Design §6.4
            ops_sheet_count=sum(1 for item in items if item.ops),
            empty_columns=list(result.empty_columns),
        )

    # ── 소스 카탈로그 (Design §2.2 P1 > P2) ─────────────────────────────────
    def _build_catalog(
        self, analysis_source, attachments, owner_user_id, request_id,
    ) -> tuple[list[RawSourceRef], list[tuple[list[str], list[list]]]]:
        catalog: list[RawSourceRef] = []
        store: list[tuple[list[str], list[list]]] = []
        for entry in analysis_source or []:
            if not isinstance(entry, dict) or entry.get("kind") != "raw_source":
                continue
            excel = entry.get("excel") or {}
            self._append_sheets(
                catalog, store, excel.get("sheets") or {},
                origin=str(entry.get("origin", "analysis")),
            )
        if not catalog:  # P1 없음 → P2: 첨부 직접 파싱
            self._append_attachments(
                catalog, store, attachments, owner_user_id, request_id
            )
        return catalog, store

    @staticmethod
    def _append_sheets(catalog, store, sheets: dict, *, origin: str) -> None:
        """ExcelData.to_dict()의 sheets 동형 dict → 카탈로그 항목 추가."""
        for name, sheet in sheets.items():
            columns = list(sheet.get("columns") or [])
            if not columns:
                continue
            data = sheet.get("data") or []
            rows = [[row.get(c) for c in columns] for row in data]
            catalog.append(RawSourceRef(
                catalog_idx=len(catalog), origin=origin,
                sheet_name=str(name), columns=columns, row_count=len(rows),
                column_dtypes=dict(sheet.get("dtypes") or {}),
            ))
            store.append((columns, rows))

    def _append_attachments(
        self, catalog, store, attachments, owner_user_id, request_id,
    ) -> None:
        if self._excel_parser is None:
            return
        for att in attachments or []:
            if att.get("type") != "excel":
                continue
            try:
                excel_data = self._excel_parser.parse(
                    att.get("file_path", ""),
                    att.get("user_id") or owner_user_id,
                )
            except Exception as e:  # 파싱 실패 원천은 제외하고 진행 (§6.1 #5)
                self._logger.warning(
                    "ExcelGenerator attachment parse skipped",
                    request_id=request_id, exception=e,
                    file_path=att.get("file_path", ""),
                )
                continue
            self._append_sheets(
                catalog, store,
                excel_data.to_dict().get("sheets") or {},
                origin="attachment",
            )

    # ── 시트 계획 (LLM 1회, Design §2.2) ────────────────────────────────────
    async def _plan_sheets(
        self, llm, catalog, sheet_store, evidence_block, conversation_block,
        request_id, worker_context_block: str = "",
    ) -> tuple[str, list[SheetPlanItem], bool]:
        """(파일명, 시트 계획, 재시도 여부). 실패 시 1회 재요청 (Design §6.1)."""
        messages = self._build_messages(
            catalog, sheet_store, evidence_block, conversation_block,
            worker_context_block,
        )
        catalog_columns = [ref.columns for ref in catalog]
        content = await self._invoke(llm, messages, "excel_generator_plan", request_id)
        filename, items, violations = self._check_plan(content, catalog_columns)
        if not violations:
            return filename, items, False

        # Plan SC-5: 위반 사유를 붙여 1회만 재요청 — LLM 호출 상한 2회
        self._logger.warning(
            "ExcelGenerator plan retry", request_id=request_id, violations=violations,
        )
        retry_messages = messages + self._retry_messages(content, violations)
        content = await self._invoke(
            llm, retry_messages, "excel_generator_plan_retry", request_id
        )
        filename, items, violations = self._check_plan(content, catalog_columns)
        if violations:
            raise ExcelGenerateError(
                "시트 계획이 유효하지 않습니다: " + "; ".join(violations)
            )
        return filename, items, True

    def _build_messages(
        self, catalog, sheet_store, evidence_block, conversation_block,
        worker_context_block: str,
    ) -> list[dict]:
        # worker-context-injection §4.1 (GAP-01): 에이전트 지침·역할을 앞단에.
        return [
            {
                "role": "system",
                "content": (
                    worker_context_block
                    + _PLAN_GUIDELINES + "\n\n"
                    + self._render_catalog(catalog, sheet_store)
                ),
            },
            {
                "role": "user",
                "content": self._build_user_content(
                    evidence_block, conversation_block
                ),
            },
        ]

    @staticmethod
    async def _invoke(llm, messages, run_name: str, request_id: str) -> str:
        config = {"run_name": run_name, "metadata": {"request_id": request_id}}
        try:
            response = await llm.ainvoke(messages, config=config)
        except Exception as e:  # noqa: BLE001 — LLM 계층 예외 전부 안내 노옵 대상 (§6.1)
            raise ExcelGenerateError(f"시트 계획 생성 오류: {e}") from e
        # thinking 상시 모델(Claude Opus 5.5 등)은 content가 블록 리스트.
        # text 블록만 이어 붙인다 (thinking 블록 제외)
        return coerce_message_text(getattr(response, "content", str(response)))

    def _check_plan(
        self, content: str, catalog_columns: list[list[str]],
    ) -> tuple[str, list[SheetPlanItem], list[str]]:
        """파싱 + 검증. 빈 계획은 위반이 아니라 '데이터 없음' (재시도 대상 아님)."""
        try:
            filename, items = self._parse_plan(content)
        except ExcelGenerateError:
            return "", [], ["JSON 파싱 실패 — 설명 없이 JSON 하나만 출력해야 합니다"]
        if not items:
            return filename, [], []
        violations = validate_plan(items, len(catalog_columns), catalog_columns)
        return filename, items, violations

    @staticmethod
    def _retry_messages(content: str, violations: list[str]) -> list[dict]:
        problems = "\n".join(f"- {v}" for v in violations)
        return [
            {"role": "assistant", "content": (content or "")[:_RETRY_ECHO_MAX_CHARS]},
            {
                "role": "user",
                "content": (
                    f"위 계획에 다음 문제가 있습니다:\n{problems}\n"
                    "문제를 고친 시트 계획 JSON만 다시 출력하라."
                ),
            },
        ]

    @staticmethod
    def _render_catalog(catalog, sheet_store) -> str:
        """원천 요약만 노출 — 전체 데이터 미노출이 무손실 경로의 전제 (§2.2)."""
        if not catalog:
            return "[원천 카탈로그]\n(구조화 원천 없음)"
        lines = ["[원천 카탈로그]"]
        for ref in catalog:
            _, rows = sheet_store[ref.catalog_idx]
            # Design §11.3: 컬럼 타입 노출 — filter·column_types 작성 근거 (FR-10)
            dtypes = f", 타입: {ref.column_dtypes}" if ref.column_dtypes else ""
            lines.append(
                f"{ref.catalog_idx}. (origin={ref.origin}) "
                f"시트 '{ref.sheet_name}' — 컬럼: {ref.columns}{dtypes}, "
                f"행수: {ref.row_count}"
            )
            lines.append(f"   샘플: {rows[:_SAMPLE_ROWS]}")
        return "\n".join(lines)

    def _build_user_content(
        self, evidence_block: str, conversation_block: str
    ) -> str:
        evidence = self._truncate(evidence_block) or "(수집된 근거 없음)"
        conversation = self._truncate(conversation_block) or "(대화 없음)"
        return f"[근거 자료]\n{evidence}\n\n[대화]\n{conversation}"

    def _truncate(self, text: str) -> str:
        return (text or "").strip()[: self._input_max_chars]

    @staticmethod
    def _parse_plan(content: str) -> tuple[str, list[SheetPlanItem]]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else ""
            text = text.rsplit("```", 1)[0]
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ExcelGenerateError("시트 계획 JSON 파싱 실패") from e
        if not isinstance(data, dict):
            raise ExcelGenerateError("시트 계획 JSON 파싱 실패")
        items = [
            SheetPlanItem(
                source=str(s.get("source", "")),
                sheet_name=str(s.get("sheet_name") or f"Sheet{i + 1}"),
                columns=s.get("columns"),
                rows=s.get("rows"),
                ops=s.get("ops"),
                column_types=s.get("column_types"),
            )
            for i, s in enumerate(data.get("sheets") or [])
            if isinstance(s, dict)
        ]
        return str(data.get("filename") or ""), items

    # ── 계획 실행 (raw 무손실 / raw+ops 코드 연산 / llm 상한 절단) ────────────
    def _materialize(
        self, items, sheet_store, request_id: str,
    ) -> tuple[list[ExcelSheetData], bool, bool]:
        sheets: list[ExcelSheetData] = []
        truncated = False
        used_raw = False
        used_names: set[str] = set()
        for item in items:
            columns, rows, cut = self._sheet_rows(item, sheet_store, request_id)
            truncated = truncated or cut
            used_raw = used_raw or parse_raw_index(item.source) is not None
            name = ExcelGenerator._unique_sheet_name(
                item.sheet_name, used_names
            )
            sheets.append(ExcelSheetData(
                sheet_name=name, columns=columns, rows=rows,
                column_types=item.column_types,
            ))
        return sheets, truncated, used_raw

    def _sheet_rows(
        self, item: SheetPlanItem, sheet_store, request_id: str,
    ) -> tuple[list[str], list[list], bool]:
        """(컬럼, 행, 절단 여부). Plan SC-1: raw+ops 결과에는 300행 상한 미적용."""
        idx = parse_raw_index(item.source)
        if idx is None:
            rows = list(item.rows or [])
            cut = len(rows) > MAX_LLM_STRUCTURED_ROWS
            return list(item.columns or []), rows[:MAX_LLM_STRUCTURED_ROWS], cut
        columns, rows = sheet_store[idx]
        if not item.ops:
            return columns, rows, False
        try:
            return apply_ops(columns, rows, item.ops)
        except Exception as e:  # noqa: BLE001 — Design §6.1 #6: 안내 노옵
            self._logger.error(
                "ExcelGenerator ops failed",
                request_id=request_id, sheet_name=item.sheet_name, exception=e,
            )
            raise ExcelGenerateError(
                f"시트 '{item.sheet_name}' 연산 실패: {e}"
            ) from e

    @staticmethod
    def _unique_sheet_name(name: str, used: set[str]) -> str:
        base = _INVALID_SHEET_CHARS.sub("_", name or "Sheet").strip() or "Sheet"
        base = base[:_MAX_SHEET_NAME_LEN]
        candidate, n = base, 2
        while candidate in used:
            suffix = f"_{n}"
            candidate = base[: _MAX_SHEET_NAME_LEN - len(suffix)] + suffix
            n += 1
        used.add(candidate)
        return candidate

    # ── 변환 + 저장 ─────────────────────────────────────────────────────────
    def _export_and_save(self, filename, sheets, owner_user_id, request_id):
        request = ExcelExportRequest(
            filename=self._safe_filename(filename),
            sheets=sheets,
            request_id=request_id,
            user_id=owner_user_id or "agent",
        )
        try:
            result = self._exporter.export(request)
            return self._store.save(
                file_bytes=result.excel_bytes,
                filename=result.filename,
                attachment_type=AttachmentType.EXCEL,
                owner_user_id=owner_user_id,
            )
        except (RuntimeError, OSError) as e:
            # Design §6.1 #6: 변환·디스크 저장 실패 모두 안내 노옵 — 그래프 비중단
            raise ExcelGenerateError(str(e)) from e

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """경로 컴포넌트 제거 + 기본값 (store 새니타이즈와 이중 방어)."""
        name = PurePath((filename or "").replace("\\", "/")).name.strip()
        if not name:
            return "output.xlsx"
        return name if name.lower().endswith(".xlsx") else f"{name}.xlsx"


def _is_blank(value) -> bool:
    if value is None or value != value:  # NaN 포함
        return True
    return isinstance(value, str) and not value.strip()


def _empty_columns(sheets) -> tuple[str, ...]:
    """행이 1개 이상인데 값이 전부 빈 컬럼 → "시트/컬럼" (claude-agent-e2e-fixes §5.6).

    예: 숫자로 해석할 수 없는 컬럼의 groupby mean.
    답변이 빈 값을 감추지 않게 노드 요약에 싣는다.
    """
    found: list[str] = []
    for sheet in sheets:
        if not sheet.rows:
            continue
        for idx, column in enumerate(sheet.columns):
            values = (row[idx] if idx < len(row) else None for row in sheet.rows)
            if all(_is_blank(v) for v in values):
                found.append(f"{sheet.sheet_name}/{column}")
    return tuple(found)
