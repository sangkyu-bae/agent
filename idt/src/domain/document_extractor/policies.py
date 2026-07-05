"""document_extractor 도메인 정책 (Design §2-2).

⚠️ 외부 의존 금지 — 정규식/문자열 처리만 사용하는 순수 규칙.
"""
import re

from src.domain.document_extractor.exceptions import (
    DocumentTooLargeError,
    InvalidDocumentError,
    InvalidSlotError,
    RegenLimitExceededError,
    TemplateTokenMismatchError,
)
from src.domain.document_extractor.schemas import SLOT_KEY_PATTERN, TemplateSlot

# html_skeleton 내 치환 토큰 탐지 — TemplateSlot.anchor와 단일 규칙 쌍
TOKEN_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

# 확장자 → source_format (v1: PDF/Word만 — Plan 결정 4 원본 포맷 따름)
_ALLOWED_EXTENSIONS: dict[str, str] = {".pdf": "pdf", ".docx": "docx"}

_VALID_SLOT_TYPES = {"value", "generated"}

_MAX_LABEL_LENGTH = 100
_MAX_TEXT_LENGTH = 300      # description / fill_hint
_MAX_SAMPLE_LENGTH = 500

DEFAULT_MAX_SLOTS = 30
MAX_SKELETON_BYTES = 5 * 1024 * 1024  # 5 MiB — MCP 변환 HTML 상한


class DocumentFilePolicy:
    """업로드 파일 검증 — 확장자/빈 파일/크기 (GA2)."""

    @staticmethod
    def resolve_format(filename: str) -> str:
        """확장자 → source_format ("pdf"|"docx"). 미허용 시 InvalidDocumentError."""
        dot = filename.rfind(".")
        ext = filename[dot:].lower() if dot != -1 else ""
        fmt = _ALLOWED_EXTENSIONS.get(ext)
        if fmt is None:
            allowed = ", ".join(sorted(_ALLOWED_EXTENSIONS))
            raise InvalidDocumentError(
                f"지원하지 않는 문서 형식입니다: {filename!r} (허용: {allowed})"
            )
        return fmt

    @classmethod
    def validate(cls, filename: str, size_bytes: int, max_file_mb: int) -> str:
        """검증 후 source_format 반환."""
        fmt = cls.resolve_format(filename)
        if size_bytes <= 0:
            raise InvalidDocumentError("빈 파일은 업로드할 수 없습니다.")
        if size_bytes > max_file_mb * 1024 * 1024:
            raise DocumentTooLargeError(
                f"파일 크기가 최대 {max_file_mb}MB를 초과했습니다."
            )
        return fmt


class SlotPolicy:
    """슬롯 규칙 — 개수/키 패턴/중복/타입/길이."""

    @staticmethod
    def validate(
        slots: list[TemplateSlot], max_slots: int = DEFAULT_MAX_SLOTS
    ) -> None:
        if not slots:
            raise InvalidSlotError("슬롯이 최소 1개 필요합니다.")
        if len(slots) > max_slots:
            raise InvalidSlotError(f"슬롯은 최대 {max_slots}개까지 허용됩니다.")
        seen: set[str] = set()
        for slot in slots:
            SlotPolicy._validate_one(slot)
            if slot.key in seen:
                raise InvalidSlotError(f"중복된 슬롯 key: {slot.key!r}")
            seen.add(slot.key)

    @staticmethod
    def _validate_one(slot: TemplateSlot) -> None:
        if not SLOT_KEY_PATTERN.match(slot.key or ""):
            raise InvalidSlotError(
                f"슬롯 key는 영소문자 시작 + [a-z0-9_] 최대 50자여야 합니다: {slot.key!r}"
            )
        if not slot.label or len(slot.label) > _MAX_LABEL_LENGTH:
            raise InvalidSlotError(
                f"슬롯 label은 1~{_MAX_LABEL_LENGTH}자 필수입니다: key={slot.key!r}"
            )
        if slot.slot_type not in _VALID_SLOT_TYPES:
            raise InvalidSlotError(
                f"slot_type은 value|generated여야 합니다: {slot.slot_type!r}"
            )
        if len(slot.description) > _MAX_TEXT_LENGTH or len(slot.fill_hint) > _MAX_TEXT_LENGTH:
            raise InvalidSlotError(
                f"description/fill_hint는 최대 {_MAX_TEXT_LENGTH}자입니다: key={slot.key!r}"
            )
        if len(slot.sample_value) > _MAX_SAMPLE_LENGTH:
            raise InvalidSlotError(
                f"sample_value는 최대 {_MAX_SAMPLE_LENGTH}자입니다: key={slot.key!r}"
            )


class TemplateTokenPolicy:
    """html_skeleton ↔ 슬롯 토큰 정합 검증 (D2 — 백엔드는 검증 전담)."""

    @staticmethod
    def validate(html_skeleton: str, slots: list[TemplateSlot]) -> None:
        if not html_skeleton or not html_skeleton.strip():
            raise TemplateTokenMismatchError("html_skeleton이 비어 있습니다.")
        if len(html_skeleton.encode("utf-8")) > MAX_SKELETON_BYTES:
            raise TemplateTokenMismatchError(
                f"html_skeleton이 최대 {MAX_SKELETON_BYTES // (1024 * 1024)}MB를 초과했습니다."
            )
        tokens = set(TOKEN_RE.findall(html_skeleton))
        slot_keys = {s.key for s in slots}
        missing = slot_keys - tokens
        if missing:
            raise TemplateTokenMismatchError(
                f"html_skeleton에 슬롯 토큰이 없습니다: {sorted(missing)}"
            )
        undefined = tokens - slot_keys
        if undefined:
            raise TemplateTokenMismatchError(
                f"슬롯에 정의되지 않은 토큰이 있습니다: {sorted(undefined)}"
            )


class RegenPolicy:
    """재추천/재생성 상한 (R5)."""

    @staticmethod
    def validate(regen_count: int, max_regen: int) -> None:
        if regen_count < 0 or regen_count >= max_regen:
            raise RegenLimitExceededError(
                f"추천 재생성 상한({max_regen}회)을 초과했습니다."
            )


class UnfilledSlotPolicy:
    """GB6: 미근거 = 공란 판정 + 하이라이트 마크업 (하드 규칙)."""

    @staticmethod
    def is_unfilled(value: str | None) -> bool:
        return value is None or not value.strip()

    @staticmethod
    def render_unfilled(slot: TemplateSlot) -> str:
        """공란 슬롯 표식 — 사람이 채울 지점을 하이라이트(Plan 결정 6).

        [미기재] 텍스트 병기(D8): html→docx 엔진(htmldocx)이 mark 배경
        스타일을 소실해도 표식이 산출물에 생존하도록 한다 (PoC 실측).
        """
        return (
            f'<mark data-unfilled="{slot.key}" '
            f'style="background:#FFF3B0">[미기재] {slot.label}</mark>'
        )


class SlotValuePolicy:
    """채움 값 정제 — 토큰 주입 방지. HTML escape는 치환기(composer) 책임."""

    @staticmethod
    def sanitize(value: str) -> str:
        return value.replace("{{", "").replace("}}", "")


class HtmlSanitizePolicy:
    """추출 HTML 방어적 정제 (R7 방어 1선 — 프론트 sandbox iframe이 2선).

    화이트리스트 파서 도입 없이 위험 요소만 제거하는 보수적 규칙:
    script/iframe/object/embed 태그, on* 이벤트 속성, javascript: URL.
    """

    _SCRIPT_RE = re.compile(
        r"<\s*(script|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
        re.IGNORECASE | re.DOTALL,
    )
    _VOID_DANGEROUS_RE = re.compile(
        r"<\s*(script|iframe|object|embed)\b[^>]*/?>", re.IGNORECASE
    )
    _EVENT_ATTR_RE = re.compile(
        r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE
    )
    _JS_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)

    @classmethod
    def clean(cls, html: str) -> str:
        cleaned = cls._SCRIPT_RE.sub("", html)
        cleaned = cls._VOID_DANGEROUS_RE.sub("", cleaned)
        cleaned = cls._EVENT_ATTR_RE.sub("", cleaned)
        cleaned = cls._JS_URL_RE.sub("", cleaned)
        return cleaned


# ── 작성/근거 지침 (D1 — 합성 프롬프트 인라인 상수, GB5·GB6) ─────────────────
COMPOSE_GUIDELINES = """당신은 등록된 문서 양식(템플릿)의 슬롯을 채우는 문서 작성 담당자입니다.

규칙 (반드시 준수):
1. 출력은 JSON 오브젝트 하나만. 모든 슬롯 key를 포함하고, 그 외 텍스트를 출력하지 않는다.
2. value 슬롯: 대화나 [근거 자료]에 명시된 사실 값만 사용한다. 단위·표기는 원문 그대로 옮긴다.
3. generated 슬롯: [근거 자료]에 있는 내용만 기반으로 서술한다. 근거에 없는 주장·수치를 만들지 않는다.
4. 근거가 없는 슬롯은 반드시 null로 둔다. 추정·창작·일반 상식으로 채우는 것을 금지한다. (미근거 = 공란)
5. 값에 HTML 태그나 {{ }} 토큰을 포함하지 않는다.
"""
