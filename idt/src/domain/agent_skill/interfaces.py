"""AgentSkillRepositoryInterface: agent_skill 저장소 추상화.

list_attached_skills는 주입에 필요한 instruction까지 한 번에 확보하기 위해
agent_skill ⨝ skill_definition 결과(SkillDefinition)를 반환한다.
infrastructure가 두 도메인 순수 엔티티를 조합 매핑하는 것은 허용된다.
"""
from abc import ABC, abstractmethod

from src.domain.agent_skill.schemas import AgentSkillLink
from src.domain.skill_builder.schemas import SkillDefinition


class AgentSkillRepositoryInterface(ABC):

    @abstractmethod
    async def attach(
        self, link: AgentSkillLink, request_id: str
    ) -> AgentSkillLink:
        """부착 1건 INSERT."""

    @abstractmethod
    async def detach(
        self, agent_id: str, skill_id: str, request_id: str
    ) -> None:
        """부착 해제(DELETE). 없어도 무에러(멱등)."""

    @abstractmethod
    async def list_links(
        self, agent_id: str, request_id: str
    ) -> list[AgentSkillLink]:
        """에이전트의 부착 연결 목록(sort_order ASC)."""

    @abstractmethod
    async def list_attached_skills(
        self, agent_id: str, request_id: str
    ) -> list[SkillDefinition]:
        """부착된 skill 본문 목록 (status='active', sort_order ASC)."""
