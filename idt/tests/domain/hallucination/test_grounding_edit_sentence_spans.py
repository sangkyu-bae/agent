"""GroundingEditPolicy.sentence_spans — answer-citation-verification S10b.

문장 제거와 인용 파서가 같은 경계를 써야 판정 결과와 최종 본문이 맞는다(Design D-06).
"""

from src.domain.hallucination.grounding_edit import GroundingEditPolicy


def _sentences(text: str) -> list[str]:
    return [text[s:e].strip() for s, e in GroundingEditPolicy.sentence_spans(text)]


def test_splits_on_terminators_and_blank_lines():
    text = "첫 문장입니다. 둘째 문장입니다!\n\n셋째 문단입니다"
    assert _sentences(text) == ["첫 문장입니다.", "둘째 문장입니다!", "셋째 문단입니다"]


def test_numbered_list_marker_is_not_a_sentence_end():
    text = "다음과 같습니다.\n1. 한도는 6억 원입니다.\n2. 만기는 30년입니다."
    assert _sentences(text) == [
        "다음과 같습니다.",
        "1. 한도는 6억 원입니다.",
        "2. 만기는 30년입니다.",
    ]


def test_spans_skip_whitespace_only_ranges_and_cover_text():
    text = "가. 나.  \n\n다."
    spans = GroundingEditPolicy.sentence_spans(text)
    assert all(text[s:e].strip() for s, e in spans)
    assert spans[0][0] == 0
