"""CitationMarkerParser — answer-citation-verification §3.2 (D-09·D-10)."""

from src.domain.answer_citation.parser import CitationMarkerParser as P

KNOWN = {1, 2, 3, 4, 5}


class TestNormalize:
    def test_comma_groups_become_separate_markers(self):
        assert P.normalize("한도는 6억 원입니다[1, 3].") == "한도는 6억 원입니다[1][3]."
        assert P.normalize("목표입니다[2,4]") == "목표입니다[2][4]"

    def test_markers_after_terminator_move_before_it(self):
        assert P.normalize("관리합니다.[1] 다음 문장") == "관리합니다[1]. 다음 문장"
        assert P.normalize("관리합니다.[1][2]") == "관리합니다[1][2]."

    def test_code_blocks_are_untouched(self):
        text = "코드 `arr[1, 2]` 와\n```\nx = y.[3]\n```\n끝."
        assert P.normalize(text) == text


class TestPairs:
    def test_one_pair_per_sentence_and_marker_with_markers_removed(self):
        pairs = P.pairs("총량 목표를 관리합니다[1]. 한도는 6억 원입니다[2][3].", KNOWN)
        assert [(p.pair_id, p.marker, p.sentence) for p in pairs] == [
            ("c1", 1, "총량 목표를 관리합니다."),
            ("c2", 2, "한도는 6억 원입니다."),
            ("c3", 3, "한도는 6억 원입니다."),
        ]

    def test_unknown_numbers_and_code_are_ignored(self):
        pairs = P.pairs("참고[9] 입니다[1]. `a[2]` 코드.", KNOWN)
        assert [(p.marker, p.sentence) for p in pairs] == [(1, "참고[9] 입니다.")]

    def test_duplicate_marker_in_same_sentence_counts_once(self):
        assert len(P.pairs("가[1] 나[1].", KNOWN)) == 1

    def test_no_markers(self):
        assert P.pairs("인용이 없는 답변입니다.", KNOWN) == ()


class TestMarkers:
    def test_positions_outside_code_only(self):
        text = "가[1]. `b[2]` 다[3]."
        hits = P.markers(text, KNOWN)
        assert [(h.marker, text[h.start : h.end]) for h in hits] == [
            (1, "[1]"),
            (3, "[3]"),
        ]


class TestStripAll:
    def test_removes_markers_outside_code(self):
        assert P.strip_all("한도[1][2]입니다. `x[3]`") == "한도입니다. `x[3]`"


def test_sentence_key_ignores_markers_and_whitespace():
    assert P.sentence_key("한도는  6억[1] 원입니다.") == P.sentence_key(
        "한도는 6억 원입니다."
    )
