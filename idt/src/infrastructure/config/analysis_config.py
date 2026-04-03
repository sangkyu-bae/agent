"""Analysis configuration from environment variables.

분석 에이전트 설정을 환경변수에서 로드합니다.
"""

from pydantic_settings import BaseSettings

from src.domain.policies.analysis_policy import (
    AnalysisQualityThreshold,
    AnalysisRetryPolicy,
)


class AnalysisConfig(BaseSettings):
    """분석 설정 (환경변수 기반)."""

    ANALYSIS_MAX_RETRIES: int = 3
    ANALYSIS_RETRY_ON_HALLUCINATION: bool = True
    ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY: bool = True

    ANALYSIS_MIN_CONFIDENCE_SCORE: float = 0.7
    ANALYSIS_MAX_HALLUCINATION_SCORE: float = 0.3

    model_config = {"env_file": ".env", "extra": "ignore"}

    def get_retry_policy(self) -> AnalysisRetryPolicy:
        """재시도 정책 팩토리."""
        return AnalysisRetryPolicy(
            max_retries=self.ANALYSIS_MAX_RETRIES,
            retry_on_hallucination=self.ANALYSIS_RETRY_ON_HALLUCINATION,
            require_web_search_on_retry=self.ANALYSIS_REQUIRE_WEB_SEARCH_ON_RETRY,
        )

    def get_quality_threshold(self) -> AnalysisQualityThreshold:
        """품질 임계값 팩토리."""
        return AnalysisQualityThreshold(
            min_confidence_score=self.ANALYSIS_MIN_CONFIDENCE_SCORE,
            max_hallucination_score=self.ANALYSIS_MAX_HALLUCINATION_SCORE,
        )
