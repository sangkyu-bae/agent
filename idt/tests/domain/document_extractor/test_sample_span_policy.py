"""SampleSpanPolicy — 예시값 위치 계산.

docx-format-preserving-fill Design §3.1, U-01~07.
"""

from src.domain.document_extractor.policies import SampleSpanPolicy


class TestFindSpan:
    def test_simple_contains(self):  # U-01
        assert SampleSpanPolicy.find_span("업체명: 한빛상사 끝", "한빛상사") == (5, 9)

    def test_whitespace_insensitive_both_ways(self):  # U-02
        text = "주식회사 한빛상사"
        assert SampleSpanPolicy.find_span(text, "주식회사\n\t\t한빛상사") == (0, 9)
        text2 = "주식회사\n한빛 상사"
        assert SampleSpanPolicy.find_span(text2, "주식회사 한빛상사") == (0, len(text2))

    def test_span_keeps_inner_whitespace_but_not_outer(self):  # U-02
        assert SampleSpanPolicy.find_span("  금 오억원  ", "금오억원") == (2, 7)

    def test_not_found_or_empty(self):  # U-03
        assert SampleSpanPolicy.find_span("abc", "xyz") is None
        assert SampleSpanPolicy.find_span("abc", "") is None
        assert SampleSpanPolicy.find_span("abc", " \n\t") is None

    def test_first_occurrence(self):  # U-04
        assert SampleSpanPolicy.find_span("2026년 2026월", "2026") == (0, 4)


class TestSplitSpan:
    def test_across_three_segments(self):  # U-05
        # 세그먼트 길이 [3, 2, 4] → 전체 "aaaBBcccc", 구간 (1, 7)
        assert SampleSpanPolicy.split_span([3, 2, 4], (1, 7)) == [
            (0, 1, 3),
            (1, 0, 2),
            (2, 0, 2),
        ]

    def test_inside_one_segment(self):  # U-06
        assert SampleSpanPolicy.split_span([5, 5], (6, 8)) == [(1, 1, 3)]

    def test_zero_length_segments_skipped(self):  # U-07
        assert SampleSpanPolicy.split_span([2, 0, 3], (1, 4)) == [(0, 1, 2), (2, 0, 2)]
