"""엑셀 생성기 도메인 예외 (excel-generator-node Design §3.3, §6.1)."""


class ExcelGenerateError(Exception):
    """시트 계획 파싱 실패·계획 무효·변환/저장 실패 등 생성 단계 오류."""


class NoExcelDataError(ExcelGenerateError):
    """엑셀로 정리할 데이터가 전혀 없음 — 노드는 수집 유도 안내로 응답 (§6.1 #2)."""
