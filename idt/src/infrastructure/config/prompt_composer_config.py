"""시스템 프롬프트 생성 설정 (환경변수 기반).

Design Ref: §NFR-07 — 모델·온도·타임아웃·도구 상한을 전부 env 로 뺀다.
CLAUDE.md §3 "config 값 하드코딩 금지".

전 항목이 기본값을 가지므로 미설정 환경에서도 동작한다 (기존 배포 무영향).

**설정 위치**: `intent` 모듈과 동일하게 전용 `*_config.py` 만 쓰고
`src/config.py` 에는 중복 정의하지 않는다. Design §11.1 은 두 곳 모두를
적었으나, 같은 값이 두 출처를 가지면 한쪽만 바뀌는 표류가 생긴다.

절단 상한 중 **섹션 항목 수·이력 턴 수는 여기 없다** — 그것들은 운영값이 아니라
도메인 정책이므로 `PromptAssemblyPolicy` 의 클래스 상수다.
"""
from pydantic_settings import BaseSettings


class PromptComposerConfig(BaseSettings):
    """프롬프트 생성 LLM 설정."""

    PROMPT_COMPOSER_MODEL: str = "gpt-4o-mini"
    PROMPT_COMPOSER_TEMPERATURE: float = 0.2
    PROMPT_COMPOSER_TIMEOUT_SEC: float = 20.0
    # 프롬프트에 실을 도구 메타 상한. 초과분은 절단하고 warning 로그를 남긴다 (R7).
    PROMPT_COMPOSER_MAX_TOOLS: int = 50
    # 킬스위치. False 면 main.py 가 라우터를 등록하지 않는다.
    PROMPT_COMPOSER_ENABLED: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}
