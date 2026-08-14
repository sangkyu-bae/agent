"""의도 분석 설정 (환경변수 기반).

Design Ref: §4.4 — 모델·온도·타임아웃·이력 길이를 전부 env 로 뺀다.
CLAUDE.md §3 "config 값 하드코딩 금지".

전 항목이 기본값을 가지므로 미설정 환경에서도 동작한다 (Plan §8.3 — 기존 배포 무영향).
"""
from pydantic_settings import BaseSettings


class IntentConfig(BaseSettings):
    """의도 분석 LLM 설정."""

    INTENT_ANALYZER_MODEL: str = "gpt-4o-mini"
    INTENT_ANALYZER_TEMPERATURE: float = 0.0
    INTENT_ANALYZER_TIMEOUT_SEC: float = 10.0
    INTENT_ANALYZER_HISTORY_LIMIT: int = 6

    model_config = {"env_file": ".env", "extra": "ignore"}
