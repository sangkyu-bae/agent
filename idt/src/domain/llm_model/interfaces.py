"""LlmModelRepositoryInterface: LLM 모델 저장소 추상화.

LLM-MODEL-REG-001 §4-3 Repository Interface.
Infrastructure layer가 이 인터페이스를 구현한다.
"""
from abc import ABC, abstractmethod

from src.domain.llm_model.entity import LlmModel


class LlmModelRepositoryInterface(ABC):
    @abstractmethod
    async def save(self, model: LlmModel, request_id: str) -> LlmModel:
        """신규 모델 저장."""

    @abstractmethod
    async def find_by_id(
        self, model_id: str, request_id: str
    ) -> LlmModel | None:
        """PK 기준 단건 조회."""

    @abstractmethod
    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> LlmModel | None:
        """(provider, model_name) 복합 키로 조회 — 중복 등록 방지용."""

    @abstractmethod
    async def find_default(self, request_id: str) -> LlmModel | None:
        """is_default=True 모델 1건 조회 (없으면 None)."""

    @abstractmethod
    async def list_active(self, request_id: str) -> list[LlmModel]:
        """is_active=True 목록 조회."""

    @abstractmethod
    async def list_all(self, request_id: str) -> list[LlmModel]:
        """활성/비활성 포함 전체 목록 조회."""

    @abstractmethod
    async def update(self, model: LlmModel, request_id: str) -> LlmModel:
        """기존 모델 수정."""

    @abstractmethod
    async def unset_all_defaults(self, request_id: str) -> None:
        """기존 is_default=1인 모든 모델을 0으로 초기화 (set_default 직전 호출)."""
