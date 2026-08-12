"""document_generator 도메인 정책 (doc-generator Design §4-2).

⚠️ 외부 의존 금지 — 정규식/문자열 처리만 사용하는 순수 규칙.
HTML sanitize는 domain.document_extractor.policies.HtmlSanitizePolicy 재사용 (D7).
"""
import re

from src.domain.document_generator.exceptions import InvalidGenerationTypeError
from src.domain.document_generator.schemas import DocumentSection

DEFAULT_MAX_SECTIONS = 20

_MAX_NAME_LENGTH = 100
_MAX_DESCRIPTION_LENGTH = 500
_MAX_TITLE_LENGTH = 100
_MAX_GUIDANCE_LENGTH = 500

_VALID_OUTPUT_FORMATS = {"pdf", "docx"}

# 산출 HTML의 섹션 heading 탐지 — SectionCoveragePolicy의 단일 규칙 출처 (D2)
_HEADING_RE = re.compile(r"<h[1-3]\b[^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class SectionPolicy:
    """섹션 아웃라인 규칙 — 개수/제목 길이·중복/guidance 길이."""

    @staticmethod
    def validate(
        sections: list[DocumentSection], max_sections: int = DEFAULT_MAX_SECTIONS
    ) -> None:
        if not sections:
            raise InvalidGenerationTypeError("섹션이 최소 1개 필요합니다.")
        if len(sections) > max_sections:
            raise InvalidGenerationTypeError(
                f"섹션은 최대 {max_sections}개까지 허용됩니다."
            )
        seen: set[str] = set()
        for section in sections:
            SectionPolicy._validate_one(section)
            key = section.title.strip()
            if key in seen:
                raise InvalidGenerationTypeError(f"중복된 섹션 제목: {key!r}")
            seen.add(key)

    @staticmethod
    def _validate_one(section: DocumentSection) -> None:
        title = (section.title or "").strip()
        if not title or len(title) > _MAX_TITLE_LENGTH:
            raise InvalidGenerationTypeError(
                f"섹션 제목은 1~{_MAX_TITLE_LENGTH}자 필수입니다: {section.title!r}"
            )
        if len(section.guidance) > _MAX_GUIDANCE_LENGTH:
            raise InvalidGenerationTypeError(
                f"섹션 guidance는 최대 {_MAX_GUIDANCE_LENGTH}자입니다: {title!r}"
            )


class GenerationTypePolicy:
    """문서 유형 본문 규칙 — 이름/설명/출력 포맷."""

    @staticmethod
    def validate(name: str, description: str, output_format: str) -> None:
        stripped = (name or "").strip()
        if not stripped or len(stripped) > _MAX_NAME_LENGTH:
            raise InvalidGenerationTypeError(
                f"문서 유형명은 1~{_MAX_NAME_LENGTH}자 필수입니다: {name!r}"
            )
        if len(description or "") > _MAX_DESCRIPTION_LENGTH:
            raise InvalidGenerationTypeError(
                f"문서 유형 설명은 최대 {_MAX_DESCRIPTION_LENGTH}자입니다."
            )
        if output_format not in _VALID_OUTPUT_FORMATS:
            raise InvalidGenerationTypeError(
                f"output_format은 {sorted(_VALID_OUTPUT_FORMATS)} 중 하나여야 합니다: "
                f"{output_format!r}"
            )


class SectionCoveragePolicy:
    """산출 HTML의 섹션 커버리지 검사 (D2 재시도 판정의 단일 규칙 출처).

    heading(h1~h3) 텍스트에 섹션 title이 포함되면 커버로 판정
    (공백 정규화 + 부분 일치 — "1. 개요 및 배경" 같은 번호 접두 허용).
    """

    @classmethod
    def missing_titles(
        cls, html: str, sections: list[DocumentSection]
    ) -> list[str]:
        headings = [
            cls._normalize(_TAG_RE.sub("", m.group(1)))
            for m in _HEADING_RE.finditer(html or "")
        ]
        missing: list[str] = []
        for section in sections:
            wanted = cls._normalize(section.title)
            if not any(wanted in heading for heading in headings):
                missing.append(section.title)
        return missing

    @staticmethod
    def _normalize(text: str) -> str:
        return _WS_RE.sub(" ", text).strip().lower()


# ── 작성 지침 (D2 — 생성 프롬프트 인라인 상수, 추출기 COMPOSE_GUIDELINES 동형) ──
GENERATE_GUIDELINES = """당신은 등록된 문서 유형의 아웃라인에 따라 문서를 작성하는 담당자입니다.

규칙 (반드시 준수):
1. 출력은 완결된 HTML 문서 조각 하나만 — 문서 제목 <h1> 1개 + 섹션별 <h2> heading.
   HTML 외의 설명·머리말·코드펜스를 출력하지 않는다.
2. 섹션 아웃라인의 제목과 순서를 그대로 따른다. 섹션 heading 텍스트에는
   해당 섹션 제목을 반드시 포함한다.
3. [근거 자료]와 [대화]에 있는 사실만 사용한다. 근거에 없는 수치·고유명사·주장을
   만들지 않는다.
4. 근거가 부족한 섹션은 지어내지 말고 본문에 "(근거 부족으로 확인이 필요합니다)"를
   명시한다.
5. 허용 태그: h1 h2 h3, p, ul ol li, table thead tbody tr th td, strong em, br.
   script·style·iframe·이미지·외부 리소스는 사용하지 않는다.
"""
