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


class UtilityLLMProviderPort(ABC):
    """보조 LLM 공급자.

    admin-default-llm-routing Design §4.1.

    의도 판정·환각 검사·요약 등 **보조 LLM 호출**이 관리자 설정 모델을
    런타임에 따라가게 하는 진입점이다. 어댑터는 완성된 ``BaseChatModel`` 이
    아니라 이 포트를 주입받아, 호출 시점마다 현재 유효한 모델을 얻는다
    (Design AD-2 — 재시작 없는 모델 교체).
    """

    @abstractmethod
    async def get(self, temperature: float = 0.0) -> BaseChatModel | None:
        """현재 유효한 보조 LLM.

        해석에 실패하면 ``None`` 을 반환한다 — 호출부는 기존 경로로 낙하한다.
        구현체는 어떤 경우에도 예외를 던지지 않는다 (Design DR-7):
        LLM 해석 실패가 사용자 요청을 실패시켜서는 안 된다.
        """

    @abstractmethod
    async def invalidate(self) -> None:
        """모델 해석 캐시를 무효화한다.

        관리자가 모델을 생성·수정·비활성화·가격변경할 때 UseCase 가 의무
        호출한다 (Design AD-3). 실패해도 예외를 던지지 않는다.
        """
