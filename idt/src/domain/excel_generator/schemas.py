"""엑셀 생성기 도메인 스키마 (excel-generator-node Design §3.1).

⚠️ 외부 의존(pandas·LangChain·파일 I/O) 금지 — 순수 값/규칙만.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RawSourceRef:
    """구조화 원천 카탈로그 항목.

    LLM에는 이 요약(컬럼·행수·샘플)만 노출되고 전체 데이터는 코드가 보관한다
    — 무손실 복사 경로의 핵심 (Design §2.2).
    """

    catalog_idx: int
    origin: str
    sheet_name: str
    columns: list[str]
    row_count: int
    # excel-generator-spec-ops Design §3.4: SheetData.dtypes — 카탈로그 타입 노출용
    column_dtypes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SheetPlanItem:
    """LLM 시트 계획 항목. source = "raw:<catalog_idx>" | "llm"."""

    source: str
    sheet_name: str
    columns: list[str] | None = None  # llm 시트 전용
    rows: list[list] | None = None    # llm 시트 전용
    # excel-generator-spec-ops Design §3.2~§3.4 (선택 필드, 없으면 기존 동작)
    ops: list[dict] | None = None   # raw 시트 전용 연산 명세
    column_types: dict[str, str] | None = None  # raw·llm 공통 의미 타입


@dataclass(frozen=True)
class ExcelGenerateResult:
    """엑셀 생성 결과 — 노드가 다운로드 링크 렌더링에 소비."""

    file_id: str
    filename: str
    sheet_count: int
    total_rows: int
    truncated: bool        # llm 시트가 행 상한으로 잘렸는지
    used_raw_source: bool  # 무손실(raw) 경로 사용 여부
    # claude-agent-e2e-fixes Design §3.5: 행이 있는데 값이 전부 빈 컬럼 "시트/컬럼"
    empty_columns: tuple[str, ...] = ()
