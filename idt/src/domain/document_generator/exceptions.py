"""document_generator 도메인 예외 (doc-generator Design §4-1).

⚠️ 외부 의존 금지 — 순수 예외 계층만.
MCP 변환 예외(McpConversionError·McpToolNotConfiguredError)는
domain.document_extractor.exceptions의 것을 재사용한다 (D7).
"""


class DocumentGeneratorError(Exception):
    """document_generator 도메인 공통 베이스."""


class InvalidGenerationTypeError(DocumentGeneratorError, ValueError):
    """문서 유형(이름/설명/섹션/포맷) 검증 실패 — 400.

    ValueError 겸용 상속: 에이전트 create/update 라우터의 기존
    `except ValueError` → 400 매핑에 라우터 무변경으로 편승한다.
    """


class GenerateError(DocumentGeneratorError):
    """런타임 생성 실패(LLM 계약 위반 재시도 후 / 변환 실패) — 파일 미생성."""
