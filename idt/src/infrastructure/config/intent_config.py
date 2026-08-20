"""의도 분석 설정 (환경변수 기반).

Design Ref: §4.4 — 모델·온도·타임아웃·이력 길이·되묻기 상한을 전부 env 로 뺀다.
CLAUDE.md §3 "config 값 하드코딩 금지".

전 항목이 기본값을 가지므로 미설정 환경에서도 동작한다 (기존 배포 무영향).

되묻기 상한 3종의 기본값은 agent_composer 의 `PlannerPolicy` 와 맞춰 두었다.
두 모듈의 출처가 다른 이유(클래스 상수 vs env)는 Design §4.4 참조 —
agent_composer 의 상한은 도메인 정책이고, intent 의 상한은 호출자마다 다를 수
있는 운영값이다.
"""
from pydantic_settings import BaseSettings

from src.domain.intent.schemas import SlotLimits


class IntentConfig(BaseSettings):
    """의도 분석 LLM 설정."""

    INTENT_ANALYZER_MODEL: str = "gpt-4o-mini"
    INTENT_ANALYZER_TEMPERATURE: float = 0.0
    INTENT_ANALYZER_TIMEOUT_SEC: float = 10.0
    INTENT_ANALYZER_HISTORY_LIMIT: int = 6
    # Design §4.4 — 되묻기 상한. 라운드 상한이 곧 LLM 호출 상한이다.
    #
    # prompt-depth FR-17 — 2 → 3. 에이전트 생성 스펙의 축이 6개가 됐고 회당 질문
    # 상한이 3이라(FR-18) 2라운드로는 물을 수 있는 축을 다 못 묻는다.
    # 이 값이 단일 출처다: `api/main.py` 가 `slot_limits()` 를 어댑터와 파이프라인
    # 양쪽에 주입하므로, 프롬프트의 "남은 라운드" 안내와 `clamp_round` 가 같은
    # 값을 본다. domain 의 `SlotLimits` 기본값(2)은 config 미주입 시 폴백이며
    # agent_composer `PlannerPolicy` 와 맞춰 둔 별개 값이라 건드리지 않는다.
    INTENT_MAX_CLARIFICATION_ROUNDS: int = 3
    INTENT_MAX_QUESTIONS_PER_ROUND: int = 3
    INTENT_MAX_OPTIONS_PER_SLOT: int = 4

    model_config = {"env_file": ".env", "extra": "ignore"}

    def slot_limits(self) -> SlotLimits:
        """domain 이 env 를 읽지 않도록 상한을 VO 로 옮겨 담는다 (규약 C3)."""
        return SlotLimits(
            max_rounds=self.INTENT_MAX_CLARIFICATION_ROUNDS,
            max_questions=self.INTENT_MAX_QUESTIONS_PER_ROUND,
            max_options_per_slot=self.INTENT_MAX_OPTIONS_PER_SLOT,
        )
