"""LLMFactory: provider 분기로 LLM 인스턴스를 생성하는 팩토리."""
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel


class LLMFactory(LLMFactoryInterface):
    """LlmModel 엔티티의 provider 필드에 따라 적절한 LLM 인스턴스를 생성한다."""

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
        if llm_model.base_url:
            kwargs["base_url"] = llm_model.base_url
        return ChatOpenAI(**kwargs)

    def _create_anthropic(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatAnthropic:
        api_key = self._resolve_api_key(llm_model)
        return ChatAnthropic(
            model=llm_model.model_name,
            api_key=api_key,
            temperature=temperature,
        )

    def _create_ollama(
        self, llm_model: LlmModel, temperature: float
    ) -> ChatOllama:
        kwargs = dict(model=llm_model.model_name, temperature=temperature)
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
