"""에이전트 생성 파이프라인 설정 (환경변수 기반) — Design §9.3.

킬스위치 기본 off (탈착형 관례 — General Chat 셀렉터와 동일). 셀렉터
파라미터는 General Chat 의 tool_selector_* 와 **독립**이다 (Plan O6):
빌더 문맥은 "누락이 과잉보다 나쁨"이라 top_k·타임아웃 기준이 다르다.

**되묻기 상한(SlotLimits)은 여기 없다** (Analysis G-02/G-03): 상한의 단일
출처는 intent 모듈의 `INTENT_MAX_*` config 다. 파이프라인이 별도 값을 가지면
어댑터 프롬프트의 "남은 라운드" 안내와 서버 재clamp 가 어긋난다 —
main.py 가 `IntentConfig.slot_limits()` 를 파이프라인에도 주입한다.
"""
from pydantic_settings import BaseSettings


class AgentPipelineConfig(BaseSettings):
    """파이프라인 활성화·셀렉터 설정."""

    # 킬스위치. False 면 main.py 가 라우터를 등록하지 않는다.
    AGENT_PIPELINE_ENABLED: bool = False
    # 빌더 문맥 셀렉터 파라미터 (General Chat 설정과 별도)
    AGENT_PIPELINE_SELECTOR_TOP_K: int = 8
    # 대화 필터(3s)보다 여유 있게 — 빌더는 후보가 카탈로그 전체라 프롬프트가
    # 길고, 사용자는 생성 1회를 기다리는 중이라 지연 민감도가 낮다.
    AGENT_PIPELINE_SELECTOR_TIMEOUT_SEC: float = 5.0

    model_config = {"env_file": ".env", "extra": "ignore"}
