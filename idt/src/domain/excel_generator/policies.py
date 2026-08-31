"""엑셀 생성 정책 (excel-generator-node Design §3.2).

llm 구조화 시트 행 상한·시트 수 상한·시트 계획 검증. 순수 로직만.
"""
from src.domain.excel_generator.schemas import SheetPlanItem

# Plan FR-04: llm 구조화 시트 행 상한 — 초과분은 절단 + truncated 안내.
MAX_LLM_STRUCTURED_ROWS = 300
# 계획 폭주 방지 상한.
MAX_SHEETS = 10

_RAW_PREFIX = "raw:"


def parse_raw_index(source: str) -> int | None:
    """'raw:<idx>' → idx. raw 형식이 아니거나 숫자가 아니면 None."""
    if not source.startswith(_RAW_PREFIX):
        return None
    try:
        return int(source[len(_RAW_PREFIX):])
    except ValueError:
        return None


def validate_plan(items: list[SheetPlanItem], catalog_size: int) -> list[str]:
    """시트 계획 검증 — 위반 사유 목록 반환 (빈 리스트 = 유효).

    llm 시트 행 상한 초과는 위반이 아니라 절단 대상이므로 여기서 걸지 않는다
    (Design §6.1 #4).
    """
    if not items:
        return ["시트 계획이 비어 있습니다"]

    violations: list[str] = []
    if len(items) > MAX_SHEETS:
        violations.append(f"시트 수가 상한({MAX_SHEETS}개)을 초과했습니다")
    for item in items:
        violations.extend(_validate_item(item, catalog_size))
    return violations


def _validate_item(item: SheetPlanItem, catalog_size: int) -> list[str]:
    if item.source == "llm":
        if not item.columns or item.rows is None:
            return [f"llm 시트 '{item.sheet_name}'에 columns/rows가 없습니다"]
        return []
    idx = parse_raw_index(item.source)
    if idx is None:
        return [f"알 수 없는 source: {item.source!r}"]
    if not 0 <= idx < catalog_size:
        return [
            f"raw 인덱스 범위 초과: {item.source!r} (카탈로그 {catalog_size}개)"
        ]
    return []
