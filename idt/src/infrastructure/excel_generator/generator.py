"""ExcelGenerator: 하이브리드 소싱 엑셀 생성기 (excel-generator-node Design §2).

시트 계획 LLM 1회 → raw 무손실 복사 / llm 상한 절단 → PandasExcelExporter 변환
→ AgentAttachmentStore 저장 (DocumentGenerator 동형).
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
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SAMPLE_ROWS = 5          # 카탈로그에 노출할 원천 샘플 행 수 (Design §2.2)
_INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
_MAX_SHEET_NAME_LEN = 31  # Excel 시트명 하드 리밋

_PLAN_GUIDELINES = (
    "너는 엑셀 파일 생성 계획을 세우는 도우미다. 아래 재료로 시트 계획 JSON만 출력하라.\n"
    "규칙:\n"
    '1. 출력은 JSON 하나: {"filename": "<파일명>.xlsx", "sheets": [...]}\n'
    "2. [원천 카탈로그]의 데이터를 전량 담을 시트는 "
    '{"source": "raw:<번호>", "sheet_name": "..."} 로 참조만 하라. '
    "카탈로그 데이터를 직접 옮겨 적지 마라.\n"
    "3. 검색 결과·대화 등 비정형 재료에서 표를 만들 때만 "
    '{"source": "llm", "sheet_name": "...", "columns": [...], "rows": [[...]]} 를 사용하라.\n'
    "4. 사용자 요청 의도(정렬·상위 N·필터)가 있으면 llm 시트로 반영하라.\n"
    '5. 정리할 데이터가 전혀 없으면 {"filename": "", "sheets": []} 를 출력하라.\n'
    "6. JSON 외 다른 텍스트를 출력하지 마라."
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
    ) -> ExcelGenerateResult:
        catalog, sheet_store = self._build_catalog(
            analysis_source, attachments, owner_user_id, request_id
        )
        filename, items = await self._plan_sheets(
            llm, catalog, sheet_store, evidence_block, conversation_block,
            request_id,
        )
        if not items:
            raise NoExcelDataError("엑셀로 정리할 데이터가 없습니다")
        violations = validate_plan(items, len(catalog))
        if violations:
            raise ExcelGenerateError(
                "시트 계획이 유효하지 않습니다: " + "; ".join(violations)
            )

        sheets, truncated, used_raw = self._materialize(items, sheet_store)
        stored = self._export_and_save(
            filename, sheets, owner_user_id, request_id
        )
        total_rows = sum(len(s.rows) for s in sheets)
        self._logger.info(
            "ExcelGenerator done",
            request_id=request_id,
            file_id=stored.file_id,
            sheet_count=len(sheets),
            total_rows=total_rows,
            truncated=truncated,
        )
        return ExcelGenerateResult(
            file_id=stored.file_id,
            filename=stored.filename,
            sheet_count=len(sheets),
            total_rows=total_rows,
            truncated=truncated,
            used_raw_source=used_raw,
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
        request_id,
    ) -> tuple[str, list[SheetPlanItem]]:
        messages = [
            {
                "role": "system",
                "content": (
                    _PLAN_GUIDELINES + "\n\n"
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
        config = {
            "run_name": "excel_generator_plan",
            "metadata": {"request_id": request_id},
        }
        try:
            response = await llm.ainvoke(messages, config=config)
        except Exception as e:  # noqa: BLE001 — LLM 계층 예외 전부 안내 노옵 대상 (§6.1)
            raise ExcelGenerateError(f"시트 계획 생성 오류: {e}") from e
        content = getattr(response, "content", str(response))
        return self._parse_plan(content)

    @staticmethod
    def _render_catalog(catalog, sheet_store) -> str:
        """원천 요약만 노출 — 전체 데이터 미노출이 무손실 경로의 전제 (§2.2)."""
        if not catalog:
            return "[원천 카탈로그]\n(구조화 원천 없음)"
        lines = ["[원천 카탈로그]"]
        for ref in catalog:
            _, rows = sheet_store[ref.catalog_idx]
            lines.append(
                f"{ref.catalog_idx}. (origin={ref.origin}) "
                f"시트 '{ref.sheet_name}' — 컬럼: {ref.columns}, "
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
        items = [
            SheetPlanItem(
                source=str(s.get("source", "")),
                sheet_name=str(s.get("sheet_name") or f"Sheet{i + 1}"),
                columns=s.get("columns"),
                rows=s.get("rows"),
            )
            for i, s in enumerate(data.get("sheets") or [])
            if isinstance(s, dict)
        ]
        return str(data.get("filename") or ""), items

    # ── 계획 실행 (raw 무손실 / llm 상한 절단) ──────────────────────────────
    @staticmethod
    def _materialize(
        items, sheet_store,
    ) -> tuple[list[ExcelSheetData], bool, bool]:
        sheets: list[ExcelSheetData] = []
        truncated = False
        used_raw = False
        used_names: set[str] = set()
        for item in items:
            idx = parse_raw_index(item.source)
            if idx is not None:
                columns, rows = sheet_store[idx]
                used_raw = True
            else:
                columns = list(item.columns or [])
                rows = list(item.rows or [])
                if len(rows) > MAX_LLM_STRUCTURED_ROWS:
                    rows = rows[:MAX_LLM_STRUCTURED_ROWS]
                    truncated = True
            name = ExcelGenerator._unique_sheet_name(
                item.sheet_name, used_names
            )
            sheets.append(
                ExcelSheetData(sheet_name=name, columns=columns, rows=rows)
            )
        return sheets, truncated, used_raw

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
