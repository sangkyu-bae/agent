"""근거 판정 도메인 — VO·힌트·재작성 사유·문장 제거.

Design Ref: draft-grounding-check v0.2 §3 (D1–D7).
"""
from src.domain.hallucination.grounding import (
    INTERNAL_LLM_TAG,
    GroundingVerdict,
    UnsupportedClaim,
)
from src.domain.hallucination.grounding_edit import GroundingEditPolicy
from src.domain.hallucination.grounding_hints import GroundingHintPolicy

SOURCES = (
    "[문의 63116] 제목: 추가대출 가능유무\n"
    "고객: 이종철, 연락처 010-****-6380\n"
    "[위키: 답변] 친절하되 단호한 말투. 문의처: 1588 1234, https://www.example-bank.co.kr/\n"
    "기준 금리 3.5%"
)


def _claim(span, severity="high", reason="근거에 없음"):
    return UnsupportedClaim(span=span, reason=reason, severity=severity)


class TestVerdict:
    def test_주장이_없으면_grounded(self):
        """D7"""
        assert GroundingVerdict(unsupported_claims=()).grounded
        assert not GroundingVerdict(unsupported_claims=(_claim("x"),)).grounded

    def test_high_만_추린다(self):
        verdict = GroundingVerdict(unsupported_claims=(_claim("a"), _claim("b", "low")))
        assert [c.span for c in verdict.high_claims] == ["a"]

    def test_근거에_글자_그대로_있는_주장은_제외한다(self):
        """L3 실측(gpt-4o): 조회 결과에 그대로 있는 '크크크론'·제목을 high 로 판정해
        첫 문장이 지워졌다. 원문 그대로 있으면 정의상 근거가 있다."""
        sources = '{"subject": "추가대출 가능유무", "content": "기존  크크크론 300만원 대출"}'
        verdict = GroundingVerdict(unsupported_claims=(
            _claim("크크크론"),
            _claim("- 제목: 추가대출 가능유무"),  # 목록 기호·라벨이 붙어도 값 부분이 근거에 있음
            _claim("대표번호: 1877-9900"),
            _claim("기존 크크크론 300만원"),  # 공백 차이만
        ))
        kept = verdict.excluding_found_in(sources)
        assert [c.span for c in kept.unsupported_claims] == ["대표번호: 1877-9900"]

    def test_짧은_구간은_제외하지_않는다(self):
        """한 글자 구간은 우연히 근거에 있을 수 있다 — 판정기 판단을 유지."""
        verdict = GroundingVerdict(unsupported_claims=(_claim("원"),))
        assert verdict.excluding_found_in("300만원") == verdict

    def test_내부_태그_상수(self):
        assert INTERNAL_LLM_TAG == "grounding_internal"


class TestHints:
    def test_근거에_없는_대표번호(self):
        """D1"""
        hints = GroundingHintPolicy.unfound_values("대표번호: 1877-9900 으로 연락", SOURCES)
        assert hints == ["전화번호 1877-9900"]

    def test_표기만_다른_근거_번호는_힌트_아님(self):
        """D2"""
        assert GroundingHintPolicy.unfound_values("문의: 1588-1234", SOURCES) == []

    def test_마스킹_값은_추출하지_않는다(self):
        """D3"""
        assert GroundingHintPolicy.unfound_values("연락처 010-****-6380", SOURCES) == []

    def test_URL_표기_차이_흡수(self):
        text = "안내: http://example-bank.co.kr"
        assert GroundingHintPolicy.unfound_values(text, SOURCES) == []

    def test_근거에_없는_URL_이메일_계좌_금리(self):
        text = (
            "https://fake.example.org/loan 참고, help@fake.org 로 메일, "
            "계좌 110-123-456789, 금리 7.2%"
        )
        hints = GroundingHintPolicy.unfound_values(text, SOURCES)
        # 힌트는 생성문 원문 그대로 — 판정기가 생성문과 대조하기 쉽게
        assert "URL https://fake.example.org/loan" in hints
        assert "이메일 help@fake.org" in hints
        assert "계좌번호 110-123-456789" in hints
        assert "금리·비율 7.2%" in hints
        assert not any(h.startswith("전화번호") for h in hints)

    def test_금리_표기_차이_흡수(self):
        assert GroundingHintPolicy.unfound_values("기준 금리 3.50%", SOURCES) == []

    def test_금액_날짜는_대상이_아니다(self):
        assert GroundingHintPolicy.unfound_values("300만원, 2026-01-04 까지", SOURCES) == []

    def test_이메일_도메인을_URL로_이중_추출하지_않는다(self):
        hints = GroundingHintPolicy.unfound_values("help@fake.org", SOURCES)
        assert hints == ["이메일 help@fake.org"]


class TestStrip:
    def test_span_포함_문장만_제거(self):
        """D4"""
        text = "안녕하세요.\n대표번호 1877-9900 으로 연락 주세요.\n감사합니다."
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim("1877-9900")])
        assert "1877-9900" not in stripped
        assert "안녕하세요." in stripped and "감사합니다." in stripped

    def test_한_줄_안의_문장_단위로_제거(self):
        text = "심사 후 안내드립니다. 대표번호 1877-9900 으로 문의하세요. 감사합니다."
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim("1877-9900")])
        assert stripped == "심사 후 안내드립니다. 감사합니다."

    def test_span_이_원문에_없으면_변경하지_않는다(self):
        """D5 — 판정기가 요약해 인용하면 오삭제하지 않는다."""
        text = "안녕하세요.\n감사합니다."
        assert GroundingEditPolicy.strip_sentences(text, [_claim("존재하지 않는 구간")]) == text

    def test_연속_빈_줄은_하나로(self):
        text = "첫 줄\n\n1877-9900 번호\n\n마지막"
        assert GroundingEditPolicy.strip_sentences(text, [_claim("1877-9900")]) == "첫 줄\n\n마지막"


class TestFeedback:
    def test_사유에_span_이유_직전글을_담는다(self):
        """D6"""
        feedback = GroundingEditPolicy.feedback("직전 초안 본문", [_claim("1877-9900", reason="근거에 없는 번호")])
        assert "[근거 검토 결과]" in feedback
        assert '"1877-9900" — 근거에 없는 번호' in feedback
        assert "[직전 글]\n직전 초안 본문" in feedback
        assert "고객센터로 문의해 주세요" in feedback


class TestStripMultiSentenceSpan:
    def test_여러_문장에_걸친_span_은_구간째_제거(self):
        text = "처음입니다. 대표번호는 1877-9900 입니다. 평일 운영합니다. 끝입니다."
        span = "대표번호는 1877-9900 입니다. 평일 운영합니다."
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim(span)])
        assert stripped == "처음입니다. 끝입니다."

    def test_줄바꿈으로_이어진_문장은_문장째_제거(self):
        """L3 실측: 초안이 문장 중간에 '  \\n' 으로 줄을 바꿔 줄 단위 제거가 조각을 남겼다."""
        text = "문의주신 추가대출 가능 여부는  \n고객님의 심사 결과에 따라 결정됩니다.\n\n감사합니다."
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim("고객님의 심사 결과에 따라 결정됩니다.")])
        assert stripped == "감사합니다."

    def test_목록_항목은_항목_단위로_제거(self):
        text = "아래로 문의 주세요.\n- 고객센터 상담\n- 앱 크크크론 메뉴에서 한도조회\n1. 영업점 방문\n감사합니다."
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim("크크크론 메뉴")])
        assert stripped == "아래로 문의 주세요.\n- 고객센터 상담\n1. 영업점 방문\n감사합니다."

    def test_번호_목록_항목_안의_span(self):
        text = "안내드립니다.\n1. 대표번호 1877-9900 으로 전화\n2. 영업점 방문"
        stripped = GroundingEditPolicy.strip_sentences(text, [_claim("1877-9900")])
        assert stripped == "안내드립니다.\n2. 영업점 방문"

    def test_span_의_공백_차이는_흡수한다(self):
        """L3 실측: 판정기가 줄 끝 공백('  \\n')을 빼고 인용해 원문 일치에 실패했다."""
        text = "안내드립니다.\n해당 채널로 문의 주시면  \n담당자가 안내드립니다.\n감사합니다."
        claim = _claim("해당 채널로 문의 주시면\n담당자가 안내드립니다.")
        assert GroundingEditPolicy.strip_sentences(text, [claim]) == "안내드립니다.\n감사합니다."

    def test_공백만_다른_span_도_없으면_변경하지_않는다(self):
        text = "안녕하세요.\n감사합니다."
        assert GroundingEditPolicy.strip_sentences(text, [_claim("안녕 하세요 고객님")]) == text

    def test_전체가_span_이면_빈_문자열(self):
        text = "대표번호 1877-9900 입니다. 감사합니다."
        assert GroundingEditPolicy.strip_sentences(text, [_claim(text)]) == ""
