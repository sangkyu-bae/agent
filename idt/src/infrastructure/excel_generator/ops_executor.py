"""원천 연산 명세(ops) 실행기 (excel-generator-spec-ops Design §3.2, §6.3).

domain 정책(validate_ops)을 통과한 명세만 받는다는 전제로 pandas로 실행한다.
숫자·날짜 해석은 비교·정렬·집계 판단에만 쓰고, 결과 셀은 원천 값 그대로 둔다.
문자열 평가(DataFrame.query/eval)는 쓰지 않는다 (Design §7).
"""
import operator
from collections.abc import Callable
from typing import Any

import pandas as pd

from src.domain.excel_generator.spec_policies import (
    EXCEL_MAX_DATA_ROWS,
    agg_output_name,
    clean_numeric_text,
    parse_date_text,
)

_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq, "!=": operator.ne,
    ">": operator.gt, ">=": operator.ge,
    "<": operator.lt, "<=": operator.le,
}


def apply_ops(
    columns: list[str], rows: list[list], ops: list[dict],
) -> tuple[list[str], list[list], bool]:
    """(결과 컬럼, 결과 행, Excel 행 한도 절단 여부).

    Plan SC-1: 결과 행에는 llm 시트 300행 상한을 적용하지 않는다.
    """
    # pandas 3.0 문자열 dtype 추론을 막아 원천 값(int·str·None)을 그대로 보존
    df = pd.DataFrame(rows, columns=columns, dtype=object)
    for op in ops:
        handler = _HANDLERS.get(op.get("op"))
        if handler is None:
            raise ValueError(f"알 수 없는 연산: {op.get('op')!r}")
        df = handler(df, op).reset_index(drop=True)
    out_rows = [
        [_native(v) for v in row]
        for row in df.itertuples(index=False, name=None)
    ]
    truncated = len(out_rows) > EXCEL_MAX_DATA_ROWS
    if truncated:
        out_rows = out_rows[:EXCEL_MAX_DATA_ROWS]
    return [str(c) for c in df.columns], out_rows, truncated


# ── 공용 값 처리 ─────────────────────────────────────────────────────────────
def _is_null(value: Any) -> bool:
    if value is None or value is pd.NaT:
        return True
    return isinstance(value, float) and value != value


def _native(value: Any) -> Any:
    """NaN·NaT → None, numpy 스칼라 → 파이썬 기본형 (exporter·JSON 안전)."""
    if _is_null(value):
        return None
    item = getattr(value, "item", None)
    return item() if callable(item) and not isinstance(value, pd.Timestamp) else value


def _text(value: Any) -> str:
    return str(value)


# ── select / top ────────────────────────────────────────────────────────────
def _apply_select(df: pd.DataFrame, op: dict) -> pd.DataFrame:
    return df[list(op["columns"])]


def _apply_top(df: pd.DataFrame, op: dict) -> pd.DataFrame:
    return df.head(int(op["n"]))


# ── filter (Design §6.3) ────────────────────────────────────────────────────
def _apply_filter(df: pd.DataFrame, op: dict) -> pd.DataFrame:
    series = df[op["col"]]
    cmp, value = op["cmp"], op.get("value")
    if cmp == "in":
        mask = _in_mask(series, value)
    elif cmp == "contains":
        mask = [not _is_null(v) and value in _text(v) for v in series]
    else:
        mask = _compare_mask(series, cmp, value)
    return df[pd.Series(mask, index=df.index, dtype=bool)]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _in_mask(series: pd.Series, values: list) -> list[bool]:
    """문자열 일치 또는 숫자 값 일치 (Check I-1: float 셀 5.0 ∈ [5]).

    숫자 일치는 value 원소가 실제 숫자일 때만 — 문자열 "001"은 글자 그대로 비교해
    앞자리 0 코드를 지킨다 (Check M-1).
    """
    texts = {_text(v) for v in values}
    numbers = {float(v) for v in values if _is_number(v)}
    mask = []
    for cell in series:
        if _is_null(cell):
            mask.append(False)
            continue
        number = clean_numeric_text(cell) if numbers else None
        mask.append(_text(cell) in texts or number in numbers)
    return mask


def _compare_mask(series: pd.Series, cmp: str, value: Any) -> list[bool]:
    """해석 방식(숫자·날짜·문자열)을 정해 비교 (Design §6.3).

    해석 불가 셀은 비교에서 제외(False)하되, '!='는 포함(True)한다.
    """
    convert, target = _comparison_mode(cmp, value)
    compare = _COMPARATORS[cmp]
    mask = []
    for cell in series:
        converted = None if _is_null(cell) else convert(cell)
        mask.append(cmp == "!=" if converted is None else compare(converted, target))
    return mask


def _comparison_mode(cmp: str, value: Any) -> tuple[Callable[[Any], Any], Any]:
    """'=='·'!='는 value가 실제 숫자일 때만 숫자 비교 (문자열은 글자 그대로, M-1).

    크기 비교는 숫자 문자열·날짜 문자열도 해석한다 — "999" > "1000" 같은
    글자 순서 비교는 거의 항상 의도와 다르다.
    """
    if cmp in ("==", "!="):
        if _is_number(value):
            return clean_numeric_text, float(value)
        return _text, _text(value)
    number = clean_numeric_text(value)
    if number is not None:
        return clean_numeric_text, number
    date = parse_date_text(value)
    if date is not None:
        return parse_date_text, date
    return _text, _text(value)


# ── sort (Design §6.3) ──────────────────────────────────────────────────────
def _apply_sort(df: pd.DataFrame, op: dict) -> pd.DataFrame:
    keys = op["by"]
    return df.sort_values(
        by=[k["col"] for k in keys],
        ascending=[not k.get("desc", False) for k in keys],
        key=_sort_key,
        na_position="last",
        kind="mergesort",
    )


def _sort_key(series: pd.Series) -> pd.Series:
    """non-null 값이 전부 숫자로 해석되면 숫자 정렬, 아니면 문자열 정렬."""
    values = [None if _is_null(v) else v for v in series]
    numbers = [None if v is None else clean_numeric_text(v) for v in values]
    all_numeric = all(n is not None for v, n in zip(values, numbers) if v is not None)
    if all_numeric:
        return pd.Series(numbers, index=series.index, dtype="float64")
    texts = [None if v is None else _text(v) for v in values]
    return pd.Series(texts, index=series.index, dtype=object)


# ── groupby (Design §3.2, §6.3) ─────────────────────────────────────────────
def _apply_groupby(df: pd.DataFrame, op: dict) -> pd.DataFrame:
    keys = list(op["by"])
    work = df[keys].copy()
    spec: dict[str, Any] = {}
    for agg in op["agg"]:
        name = agg_output_name(agg)
        source = df[agg["col"]]
        if agg["fn"] == "count":  # non-null 개수 (해석 불가 값도 값으로 셈)
            work[name] = [0 if _is_null(v) else 1 for v in source]
            spec[name] = "sum"
        else:
            work[name] = pd.Series(
                [None if _is_null(v) else clean_numeric_text(v) for v in source],
                index=df.index, dtype="float64",
            )
            spec[name] = _AGG_FUNCS[agg["fn"]]
    grouped = work.groupby(keys, dropna=False, sort=False).agg(spec)
    return grouped.reset_index()


def _sum_or_none(series: pd.Series) -> float:
    # 숫자 값이 하나도 없는 그룹은 0이 아니라 빈 값 (데이터 없음 ≠ 0)
    return series.sum(min_count=1)


_AGG_FUNCS: dict[str, Any] = {
    "sum": _sum_or_none, "mean": "mean", "min": "min", "max": "max",
}

_HANDLERS: dict[str, Callable[[pd.DataFrame, dict], pd.DataFrame]] = {
    "select": _apply_select,
    "filter": _apply_filter,
    "sort": _apply_sort,
    "top": _apply_top,
    "groupby": _apply_groupby,
}
