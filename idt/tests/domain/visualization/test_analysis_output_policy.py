"""AnalysisOutputSanitizer 테스트. Domain: mock 금지, 순수 단위테스트.

분석 노드가 프롬프트를 어기고 코드블록/JSON을 섞어 내보내도, chart_router/
evaluate_hallucination이 깨끗한 자연어만 받도록 제거하는지 검증한다.
차트 원재료가 되는 수치 배열([1,2,3])은 보존해야 한다.
"""
from src.domain.visualization.analysis_output_policy import (
    ANALYSIS_OUTPUT_SANITIZER,
    AnalysisOutputSanitizer,
)


class TestStripFencedBlocks:
    def test_strip_json_fence(self) -> None:
        s = AnalysisOutputSanitizer()
        text = '배상규 5일.\n```json\n{"a": 1}\n```'
        assert s.strip(text) == "배상규 5일."

    def test_strip_python_fence(self) -> None:
        s = AnalysisOutputSanitizer()
        text = "분석 결과.\n```python\nimport matplotlib\nx = 1\n```"
        assert s.strip(text) == "분석 결과."


class TestStripRawJson:
    def test_strip_raw_object(self) -> None:
        s = AnalysisOutputSanitizer()
        text = '결과: {"type": "bar", "data": [1, 2]}'
        assert s.strip(text) == "결과:"

    def test_strip_object_array(self) -> None:
        s = AnalysisOutputSanitizer()
        text = '[{"x": 1}, {"x": 2}] 추세'
        assert s.strip(text) == "추세"


class TestPreserveNaturalText:
    def test_preserve_numeric_array(self) -> None:
        """차트 원재료인 수치 배열은 제거하지 않는다."""
        s = AnalysisOutputSanitizer()
        text = "값은 [1, 2, 3] 입니다"
        assert s.strip(text) == "값은 [1, 2, 3] 입니다"

    def test_preserve_plain_numbers(self) -> None:
        s = AnalysisOutputSanitizer()
        text = "사용자별 남은 휴가 — 배상규 5일, 김철수 3일"
        assert s.strip(text) == "사용자별 남은 휴가 — 배상규 5일, 김철수 3일"

    def test_preserve_unbalanced_brace(self) -> None:
        s = AnalysisOutputSanitizer()
        text = "수식 { 미완성"
        assert s.strip(text) == "수식 { 미완성"

    def test_idempotent(self) -> None:
        s = AnalysisOutputSanitizer()
        text = "배상규 5일, 김철수 3일"
        assert s.strip(s.strip(text)) == text


class TestEdgeCases:
    def test_empty(self) -> None:
        assert AnalysisOutputSanitizer().strip("") == ""

    def test_none(self) -> None:
        assert AnalysisOutputSanitizer().strip(None) is None  # type: ignore[arg-type]

    def test_module_singleton_available(self) -> None:
        assert isinstance(ANALYSIS_OUTPUT_SANITIZER, AnalysisOutputSanitizer)
