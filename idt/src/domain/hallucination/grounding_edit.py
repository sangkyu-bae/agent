"""근거 판정 결과 반영 — 재작성 사유와 상한 초과 시 문장 제거.

Design Ref: draft-grounding-check v0.2 §3.3 (D-07).
"""
import re

from src.domain.hallucination.grounding import UnsupportedClaim

_TERMINATOR = re.compile(r"[.?!。](?=\s|$)")
_NUMBERED_ITEM = re.compile(r"(?m)^[ \t]*\d+[.)]")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")
_LIST_ITEM_START = re.compile(r"\n(?=[ \t]*(?:[-*•·]|\d+[.)])[ \t])")
_BLANK_RUN = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)*")


class GroundingEditPolicy:
    @staticmethod
    def feedback(previous: str, claims: list[UnsupportedClaim] | tuple) -> str:
        """재작성 지시. 주장 원문을 담는다 — LLM 입력 전용(로그 금지)."""
        lines = "\n".join(f'- "{c.span}" — {c.reason}' for c in claims)
        return (
            "[근거 검토 결과] 직전 글의 다음 내용은 제공된 근거"
            "(지침·위키·조회 결과·대화)로 확인되지 않습니다:\n"
            f"{lines}\n"
            "이 내용과 그것을 안내하는 문장을 빼거나, 값 없이 안내하도록"
            "(예: '고객센터로 문의해 주세요') 다시 작성하세요.\n"
            "근거로 확인된 나머지 내용과 어조는 유지하세요.\n\n"
            f"[직전 글]\n{previous}"
        )

    @classmethod
    def strip_sentences(cls, text: str, claims: list[UnsupportedClaim] | tuple) -> str:
        """span 을 포함한 문장을 제거한다. 원문에 없는 span 은 무시(오삭제 방지).

        문장 경계는 글 전체 기준이다 — 마침표류, 빈 줄, 목록 항목 시작.
        L3 실측: 초안이 문장 중간에 '  \\n' 으로 줄을 바꿔, 줄 단위로 자르면
        "가능 여부는" 같은 조각이 남았다.
        """
        matches = [
            m for c in claims if c.span.strip()
            for m in cls._span_pattern(c.span).finditer(text)
        ]
        if not matches:
            return text
        bounds = cls._boundaries(text)
        ranges = sorted(cls._enclosing(bounds, m.start(), m.end()) for m in matches)
        out, cursor = [], 0
        for start, end in ranges:
            if start >= cursor:
                out.append(text[cursor:start])
            cursor = max(cursor, end)
        out.append(text[cursor:])
        return _BLANK_RUN.sub("\n\n", "".join(out)).strip()

    @staticmethod
    def _span_pattern(span: str) -> re.Pattern:
        """공백 차이만 흡수한 원문 일치 — 판정기는 줄 끝 공백('  \\n')을 빼고 인용한다."""
        return re.compile(r"\s+".join(re.escape(token) for token in span.split()))

    @staticmethod
    def _boundaries(text: str) -> list[int]:
        """문장이 시작·끝날 수 있는 위치. 번호 목록의 '1.' 은 끝 경계가 아니다."""
        numbering = {m.end() - 1 for m in _NUMBERED_ITEM.finditer(text)}
        points = {0, len(text)}
        points.update(m.end() for m in _TERMINATOR.finditer(text) if m.start() not in numbering)
        for m in _PARAGRAPH_BREAK.finditer(text):
            points.update((m.start(), m.end()))
        points.update(m.start() for m in _LIST_ITEM_START.finditer(text))
        return sorted(points)

    @staticmethod
    def _enclosing(bounds: list[int], start: int, end: int) -> tuple[int, int]:
        left = max(b for b in bounds if b <= start)
        right = min(b for b in bounds if b >= end)
        return left, right
