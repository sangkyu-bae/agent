"""QualityGatePolicy 단위 테스트 (TC-13~15)."""
import pytest

from src.domain.agent_builder.policies import QualityGatePolicy


class TestQualityGatePolicy:
    def test_empty_string_returns_false(self):
        """TC-13: 빈 응답 → False."""
        assert QualityGatePolicy.check_response("") is False

    def test_none_returns_false(self):
        assert QualityGatePolicy.check_response(None) is False

    def test_short_string_returns_false(self):
        assert QualityGatePolicy.check_response("짧음") is False

    def test_whitespace_only_returns_false(self):
        assert QualityGatePolicy.check_response("         ") is False

    def test_normal_response_returns_true(self):
        """TC-14: 정상 응답 → True."""
        assert QualityGatePolicy.check_response("검색 결과 AI 뉴스를 정리했습니다.") is True

    def test_starts_with_unknown_indicator_returns_false(self):
        """TC-15: '모르겠습니다' 시작 → False."""
        assert QualityGatePolicy.check_response("모르겠습니다. 해당 정보를 찾을 수 없습니다.") is False

    def test_starts_with_cannot_answer_returns_false(self):
        assert QualityGatePolicy.check_response("답변할 수 없습니다. 권한이 부족합니다.") is False

    def test_starts_with_no_info_returns_false(self):
        assert QualityGatePolicy.check_response("정보를 찾을 수 없습니다.") is False

    def test_indicator_in_middle_returns_true(self):
        """빈 지표가 중간에 있으면 통과."""
        assert QualityGatePolicy.check_response("결과: 모르겠습니다라고 답할 수도 있지만 정보를 찾았습니다.") is True

    def test_exactly_min_length_returns_true(self):
        content = "a" * QualityGatePolicy.MIN_RESPONSE_LENGTH
        assert QualityGatePolicy.check_response(content) is True

    def test_below_min_length_returns_false(self):
        content = "a" * (QualityGatePolicy.MIN_RESPONSE_LENGTH - 1)
        assert QualityGatePolicy.check_response(content) is False
