"""LLMFactoryInterface: LLM 인스턴스 생성 팩토리 추상화.

Application 레이어가 이 인터페이스에 의존하여
provider 구현체와 결합하지 않는다.
"""
from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel

from src.domain.llm_model.entity import LlmModel


class LLMFactoryInterface(ABC):
    """LlmModel 엔티티 기반 LLM 인스턴스 팩토리."""

    @abstractmethod
    def create(
        self,
        llm_model: LlmModel,
        temperature: float = 0.0,
    ) -> BaseChatModel:
        """provider에 맞는 LLM 인스턴스를 생성한다."""
