"""LlmModel 도메인 엔티티.

LLM-MODEL-REG-001: LLM 모델 레지스트리 도메인 객체.
외부 시스템(OpenAI/Anthropic/Ollama 등) 호출 없이 순수 값만 보관한다.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class LlmModel:
    """등록된 LLM 모델 한 건.

    Attributes:
        id: PK (UUID)
        provider: "openai" | "anthropic" | "ollama" | "perplexity"
        model_name: 실제 API 호출명 (e.g. "gpt-4o")
        display_name: UI 표시명 (e.g. "GPT-4o")
        description: 모델 특징 설명
        api_key_env: 참조할 환경변수명 (e.g. "OPENAI_API_KEY")
        max_tokens: 최대 컨텍스트 토큰 수
        is_active: False 시 선택 불가 (소프트 삭제)
        is_default: True 시 기본 선택 모델 (전체에서 1개만 허용)
        created_at: 생성 시각
        updated_at: 최종 수정 시각
        input_price_per_1k_usd: 입력 토큰 1000개당 USD (AGENT-OBS-001)
        output_price_per_1k_usd: 출력 토큰 1000개당 USD
        pricing_updated_at: 가격 최종 갱신 시각
        base_url: self-host 엔드포인트(vLLM/OpenAI 호환 등). None이면 provider 기본값 (LLM-MODEL-REG-002)
    """

    id: str
    provider: str
    model_name: str
    display_name: str
    description: str | None
    api_key_env: str
    max_tokens: int | None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    input_price_per_1k_usd: Decimal | None = None
    output_price_per_1k_usd: Decimal | None = None
    pricing_updated_at: datetime | None = None
    base_url: str | None = None
