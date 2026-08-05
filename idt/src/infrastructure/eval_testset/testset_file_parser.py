"""테스트셋 파일 파서 — CSV/XLSX 확장자 라우팅 (eval-hub Design A5).

kb-excel-upload 확장자 라우팅 패턴. 파싱 실패는 ValueError로 표면화해
라우터에서 422로 편승한다.
"""
import csv
import io

# 열 이름 별칭 → 표준 키
_QUESTION_ALIASES = {"question", "질문"}
_GROUND_TRUTH_ALIASES = {"ground_truth", "정답", "답변", "answer"}


def parse_testset_file(file_bytes: bytes, filename: str) -> list[dict]:
    """CSV/XLSX 바이트를 [{question, ground_truth}] 케이스 목록으로 파싱한다."""
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        rows = _read_csv(file_bytes)
    elif lowered.endswith((".xlsx", ".xls")):
        rows = _read_excel(file_bytes)
    else:
        raise ValueError(
            "지원하지 않는 파일 형식입니다 (.csv, .xlsx만 가능)"
        )
    return _rows_to_cases(rows)


def _read_csv(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row) for row in reader]


def _read_excel(file_bytes: bytes) -> list[dict]:
    import pandas as pd

    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    df = df.where(df.notna(), None)
    return df.to_dict(orient="records")


def _rows_to_cases(rows: list[dict]) -> list[dict]:
    if rows:
        _validate_columns(rows[0])
    cases: list[dict] = []
    for row in rows:
        question = _pick(row, _QUESTION_ALIASES)
        if not question:
            continue  # 질문 빈 행 스킵
        cases.append({
            "question": question,
            "ground_truth": _pick(row, _GROUND_TRUTH_ALIASES),
        })
    if not cases:
        raise ValueError("유효한 QA 행이 없습니다 (question/질문 컬럼 확인)")
    return cases


def _validate_columns(first_row: dict) -> None:
    keys = {str(k).strip().lower() for k in first_row if k}
    if not keys & {a.lower() for a in _QUESTION_ALIASES}:
        raise ValueError("question(질문) 컬럼이 없습니다")


def _pick(row: dict, aliases: set[str]) -> str | None:
    for key, value in row.items():
        if key and str(key).strip().lower() in {a.lower() for a in aliases}:
            if value is None:
                return None
            text = str(value).strip()
            return text or None
    return None
