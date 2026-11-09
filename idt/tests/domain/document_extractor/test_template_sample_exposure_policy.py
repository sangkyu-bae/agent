"""TemplateSampleExposurePolicy 단위 테스트 (extractor-template-preview Design §4.2-6).

예시값(sample_value)은 원본 문서의 실값이라, 양식을 만든 에이전트의 소유자에게만 보인다.
"""
from src.domain.document_extractor.policies import TemplateSampleExposurePolicy


class TestTemplateSampleExposurePolicy:
    def test_origin_owner_can_view_samples(self):
        assert (
            TemplateSampleExposurePolicy.can_view_samples("user-1", "user-1") is True
        )

    def test_other_user_cannot_view_samples(self):
        # 포크로 양식을 물려받은 사용자
        assert not TemplateSampleExposurePolicy.can_view_samples("user-2", "user-1")

    def test_unknown_origin_owner_hides_samples(self):
        # 원 에이전트가 삭제돼 소유자를 알 수 없으면 숨긴다
        assert TemplateSampleExposurePolicy.can_view_samples("user-2", None) is False
