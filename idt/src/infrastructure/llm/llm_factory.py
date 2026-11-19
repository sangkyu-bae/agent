"""LLMFactory: provider 분기로 LLM 인스턴스를 생성하는 팩토리."""
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm.sampling_policy import (
    anthropic_accepts_temperature,
    anthropic_supports_forced_tool_choice,
    resolve_max_output_tokens,
)
from src.domain.llm_model.entity import LlmModel
from src.infrastructure.llm.structured_chat_anthropic import (
    JsonSchemaStructuredChatAnthropic,
)


class LLMFactory(LLMFactoryInterface):
    """LlmModel 엔티티의 provider 필드에 따라 적절한 LLM 인스턴스를 생성한다."""

    def __init__(self, anthropic_default_max_output_tokens: int = 16000) -> None:
        # claude-agent-e2e-fixes §5.1: llm_model.max_output_tokens
        # 미설정 시 Anthropic 기본값
        self._anthropic_default_max_output_tokens = anthropic_default_max_output_tokens

    def _max_output_tokens(self, llm_model: LlmModel) -> int | None:
        return resolve_max_output_tokens(
            llm_model.provider, llm_model.max_output_tokens,
            self._anthropic_default_max_output_tokens,
        )

    def create(
        self,
        llm_model: LlmModel,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        provider = llm_model.provider
        if provider == "openai":
            return self._create_openai(llm_model, temperature)
        if provider == "anthropic":
            return self._create_anthropic(llm_model, temperature)
        if provider == "ollama":
            return self._create_ollama(llm_model, temperature)
        raise ValueError(f"지원하지 않는 provider: {provider}")

    def _create_openai(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatOpenAI:
        # LLM-MODEL-REG-002: self-host(base_url) 시 인증 없는 vLLM도 허용 → 더미키.
        api_key = self._resolve_api_key(
            llm_model, allow_empty=bool(llm_model.base_url)
        )
        # AGENT-OBS-001 §14-3: streaming 응답에서도 usage_metadata 보장.
        kwargs = dict(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
            stream_usage=True,
        )
        max_out = self._max_output_tokens(llm_model)
        if max_out is not None:  # 저장값이 있을 때만 (기본은 무변경)
            kwargs["max_tokens"] = max_out
        if llm_model.base_url:
            kwargs["base_url"] = llm_model.base_url
        return ChatOpenAI(**kwargs)

    def _create_anthropic(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatAnthropic:
        api_key = self._resolve_api_key(llm_model)
        kwargs = dict(model=llm_model.model_name, api_key=api_key)
        # Claude Opus 4.7 이후 모델은 temperature를 400으로 거부 — 구형 모델에만 전달
        if anthropic_accepts_temperature(llm_model.model_name):
            kwargs["temperature"] = temperature
        kwargs["max_tokens"] = self._max_output_tokens(llm_model)
        # claude-agent-e2e-fixes §5.1: 강제 tool_choice 거부 모델은
        # 구조화 출력을 json_schema 로 받는 하위 클래스
        if anthropic_supports_forced_tool_choice(llm_model.model_name):
            return ChatAnthropic(**kwargs)
        return JsonSchemaStructuredChatAnthropic(**kwargs)

    def _create_ollama(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatOllama:
        kwargs = dict(model=llm_model.model_name, temperature=temperature)
        max_out = self._max_output_tokens(llm_model)
        if max_out is not None:  # 저장값이 있을 때만 (기본은 무변경)
            kwargs["num_predict"] = max_out
        # LLM-MODEL-REG-002: 원격/self-host Ollama 엔드포인트 지원.
        if llm_model.base_url:
            kwargs["base_url"] = llm_model.base_url
        return ChatOllama(**kwargs)

    def _resolve_api_key(
        self, llm_model: LlmModel, allow_empty: bool = False
    ) -> str:
        api_key = os.environ.get(llm_model.api_key_env, "")
        if not api_key:
            # vLLM 등 인증 미사용 self-host 엔드포인트는 더미키로 통과.
            if allow_empty:
                return "EMPTY"
            raise RuntimeError(
                f"환경변수 '{llm_model.api_key_env}'가 설정되지 않았습니다. "
                f"provider={llm_model.provider}, model={llm_model.model_name}"
            )
        return api_key
