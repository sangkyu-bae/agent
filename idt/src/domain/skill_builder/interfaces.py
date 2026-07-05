"""SkillRepositoryInterface: skill_definition 저장소 추상화."""
from abc import ABC, abstractmethod

from src.domain.skill_builder.schemas import SkillDefinition


class SkillRepositoryInterface(ABC):

    @abstractmethod
    async def save(self, skill: SkillDefinition, request_id: str) -> SkillDefinition:
        """INSERT."""

    @abstractmethod
    async def find_by_id(
        self, skill_id: str, request_id: str
    ) -> SkillDefinition | None:
        """PK 단건 조회 (삭제 포함)."""

    @abstractmethod
    async def update(self, skill: SkillDefinition, request_id: str) -> SkillDefinition:
        """UPDATE."""

    @abstractmethod
    async def list_by_user(
        self, user_id: str, request_id: str
    ) -> list[SkillDefinition]:
        """user_id 기준 목록 조회 (status='active')."""

    @abstractmethod
    async def list_accessible(
        self,
        viewer_user_id: str,
        viewer_department_ids: list[str],
        scope: str,
        search: str | None,
        page: int,
        size: int,
        request_id: str,
    ) -> tuple[list[SkillDefinition], int]:
        """가시성 기반 skill 목록 + 전체 건수."""

    @abstractmethod
    async def soft_delete(self, skill_id: str, request_id: str) -> None:
        """status='deleted'로 소프트 삭제."""
