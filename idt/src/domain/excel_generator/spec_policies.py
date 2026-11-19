"""엑셀 시트 명세 정책 (excel-generator-spec-ops Design §3.2~§3.5).

LLM이 쓴 연산 명세(ops)·컬럼 의미 타입(column_types)의 허용 목록 검증과
셀 값 변환 규칙. ⚠️ 외부 의존(pandas·openpyxl·LangChain) 금지 — 순수 로직만.
"""
import datetime
import re
from collections.abc import Callable
from typing import Any

ALLOWED_OPS = frozenset({"select", "filter", "sort", "top", "groupby"})
ALLOWED_CMPS = frozenset({"==", "!=", ">", ">=", "<", "<=", "contains", "in"})
ALLOWED_AGG_FNS = frozenset({"sum", "mean", "count", "min", "max"})
SEMANTIC_TYPES = frozenset(
    {"text", "integer", "number", "currency", "percent", "date"}
)
# Design §3.3 — 의미 타입 → openpyxl number_format
NUMBER_FORMATS: dict[str, str] = {
    "text": "General",
    "integer": "#,##0",
    "number": "#,##0.00",
    "currency": "#,##0",
    "percent": "0.0%",
    "date": "yyyy-mm-dd",
}
MAX_OPS_PER_SHEET = 10
EXCEL_MAX_DATA_ROWS = 1_048_575  # 시트 최대 1,048,576행 - 헤더 1행

_NUMERIC_RE = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)")
_DATE_RE = re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})")
_CURRENCY_MARKS = ("₩", "$")


# ── ops 검증 (Design §3.2) ──────────────────────────────────────────────────
def validate_ops(ops: Any, columns: list[str]) -> tuple[list[str], list[str]]:
    """(위반 사유 목록, 연산 후 결과 컬럼).

    컬럼 집합을 연산 순서대로 추적한다 — select로 빠진 컬럼은 이후 참조 불가,
    groupby 결과 컬럼(by + 집계 이름)은 이후 참조 가능.
    """
    if not isinstance(ops, list):
        return ["ops는 배열이어야 합니다"], list(columns)
    if len(ops) > MAX_OPS_PER_SHEET:
        return [f"ops 수가 상한({MAX_OPS_PER_SHEET}개)을 초과했습니다"], list(columns)
    current = list(columns)
    violations: list[str] = []
    for i, op in enumerate(ops):
        errors, current = _validate_one(op, current)
        violations.extend(f"ops[{i}] {e}" for e in errors)
    return violations, current


def agg_output_name(agg: dict) -> str:
    """집계 결과 컬럼명 — as 우선, 없으면 '{col}_{fn}'."""
    alias = agg.get("as")
    if isinstance(alias, str) and alias.strip():
        return alias.strip()
    return f"{agg.get('col')}_{agg.get('fn')}"


def _validate_one(op: Any, columns: list[str]) -> tuple[list[str], list[str]]:
    if not isinstance(op, dict):
        return ["연산은 객체여야 합니다"], columns
    validator = _VALIDATORS.get(op.get("op"))
    if validator is None:
        return [f"알 수 없는 연산: {op.get('op')!r}"], columns
    return validator(op, columns)


def _missing(names: list, columns: list[str]) -> list[str]:
    return [f"없는 컬럼: {n!r}" for n in names if n not in columns]


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(v, str) for v in value
    )


def _validate_select(op: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    selected = op.get("columns")
    if not _is_str_list(selected):
        return ["select.columns는 1개 이상의 컬럼명 배열이어야 합니다"], columns
    errors = _missing(selected, columns)
    # Check M-4: 중복 열은 이후 참조 시 실행 오류
    if len(set(selected)) != len(selected):
        errors.append("select.columns에 중복 컬럼이 있습니다")
    return errors, (columns if errors else list(selected))


def _validate_filter(op: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    errors = _missing([op.get("col")], columns)
    cmp, value = op.get("cmp"), op.get("value")
    if cmp not in ALLOWED_CMPS:
        errors.append(f"알 수 없는 비교 연산자: {cmp!r}")
    elif cmp == "in" and not isinstance(value, list):
        errors.append("in 비교의 value는 배열이어야 합니다")
    elif cmp == "contains" and not isinstance(value, str):
        errors.append("contains 비교의 value는 문자열이어야 합니다")
    elif cmp not in ("in", "contains") and (
        value is None or isinstance(value, (list, dict))
    ):
        # Check M-3: value 누락·null은 "None" 문자열 비교로 새지 않게 거부
        errors.append(f"{cmp} 비교의 value는 null이 아닌 단일 값이어야 합니다")
    return errors, columns


def _validate_sort(op: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    keys = op.get("by")
    if not isinstance(keys, list) or not keys:
        return ["sort.by는 1개 이상의 정렬 키 배열이어야 합니다"], columns
    errors: list[str] = []
    for key in keys:
        if not isinstance(key, dict):
            errors.append("정렬 키는 {col, desc} 객체여야 합니다")
            continue
        errors.extend(_missing([key.get("col")], columns))
        if not isinstance(key.get("desc", False), bool):  # Check M-2
            errors.append("정렬 키의 desc는 true/false여야 합니다")
    return errors, columns


def _validate_top(op: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    n = op.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        return ["top.n은 1 이상의 정수여야 합니다"], columns
    return [], columns


def _validate_groupby(op: dict, columns: list[str]) -> tuple[list[str], list[str]]:
    keys, aggs = op.get("by"), op.get("agg")
    if not _is_str_list(keys):
        return ["groupby.by는 1개 이상의 컬럼명 배열이어야 합니다"], columns
    if not isinstance(aggs, list) or not aggs:
        return ["groupby.agg는 1개 이상의 집계 배열이어야 합니다"], columns
    errors = _missing(keys, columns)
    for agg in aggs:
        errors.extend(_validate_agg(agg, columns))
    if errors:
        return errors, columns
    names = [agg_output_name(a) for a in aggs]
    result = list(keys) + names
    if len(set(result)) != len(result):
        return ["groupby 결과 컬럼명이 중복됩니다"], columns
    return [], result


def _validate_agg(agg: Any, columns: list[str]) -> list[str]:
    if not isinstance(agg, dict):
        return ["집계는 {col, fn, as} 객체여야 합니다"]
    errors = _missing([agg.get("col")], columns)
    if agg.get("fn") not in ALLOWED_AGG_FNS:
        errors.append(f"알 수 없는 집계 함수: {agg.get('fn')!r}")
    return errors


_VALIDATORS: dict[str, Callable[[dict, list[str]], tuple[list[str], list[str]]]] = {
    "select": _validate_select,
    "filter": _validate_filter,
    "sort": _validate_sort,
    "top": _validate_top,
    "groupby": _validate_groupby,
}


# ── column_types 검증 (Design §3.3) ─────────────────────────────────────────
def validate_column_types(column_types: Any, columns: list[str]) -> list[str]:
    """허용 의미 타입·존재 컬럼만 통과."""
    if not isinstance(column_types, dict):
        return ["column_types는 {컬럼명: 타입} 객체여야 합니다"]
    errors = _missing(list(column_types), columns)
    errors.extend(
        f"알 수 없는 컬럼 타입: {t!r}"
        for t in column_types.values()
        if t not in SEMANTIC_TYPES
    )
    return errors


# ── 셀 값 해석·변환 (Design §3.3, §6.3) ─────────────────────────────────────
def clean_numeric_text(value: Any) -> float | None:
    """숫자·숫자 문자열 → float. 천 단위 ','·통화 기호·접미 '원' 제거. 실패 시 None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None if value != value else float(value)  # NaN 제외
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    for mark in _CURRENCY_MARKS:
        text = text.replace(mark, "")
    text = text.removesuffix("원").strip()
    if not _NUMERIC_RE.fullmatch(text):
        return None
    return float(text)


def parse_date_text(value: Any) -> datetime.datetime | None:
    """날짜 문자열·date·datetime → datetime. 실패 시 None."""
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    text = value.strip()
    match = _DATE_RE.fullmatch(text)
    try:
        if match:
            return datetime.datetime(*(int(g) for g in match.groups()))
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def coerce_cell(value: Any, semantic_type: str) -> Any:
    """의미 타입에 맞춰 셀 값 변환. 빈 값은 None, 변환 실패는 원값."""
    converter = _CONVERTERS.get(semantic_type)
    if converter is None:  # text·알 수 없는 타입 — 그대로
        return value
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    converted = converter(value)
    return value if converted is None else converted


def _to_integer_like(value: Any) -> int | float | None:
    number = clean_numeric_text(value)
    if number is None:
        return None
    return int(number) if number.is_integer() else number


def _to_percent(value: Any) -> float | None:
    if isinstance(value, str) and value.strip().endswith("%"):
        number = clean_numeric_text(value.strip()[:-1])
        return None if number is None else number / 100
    return clean_numeric_text(value)


_CONVERTERS: dict[str, Callable[[Any], Any]] = {
    "integer": _to_integer_like,
    "currency": _to_integer_like,
    "number": clean_numeric_text,
    "percent": _to_percent,
    "date": parse_date_text,
}
