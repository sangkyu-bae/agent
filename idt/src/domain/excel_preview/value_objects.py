"""excel-preview 도메인 값 객체 (Design §3.1).

리더(infrastructure)가 생성하고 유스케이스(application)가 응답 스키마로 변환한다.
외부 라이브러리 의존 없음 — 표준 lib만 (domain 규칙).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ExcelSheetData:
    """시트 1개의 프리뷰 데이터. 모든 셀 값은 직렬화된 문자열."""

    name: str
    columns: list[str]        # 첫 행(헤더). 빈 셀 "". 행 0개면 []
    rows: list[list[str]]     # 2행째부터 상한까지, 헤더 폭으로 패딩
    total_rows: int           # 전체 행 수 (Design §3.4 산출 규칙)
    total_cols: int           # 전체 열 수
    truncated: bool           # 행/열이 상한에 걸려 잘렸는가
