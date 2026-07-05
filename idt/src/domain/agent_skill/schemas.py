"""도메인 스키마: AgentSkillLink — 에이전트 ↔ Skill 부착(주입) 연결 단위."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AgentSkillLink:
    """에이전트에 부착된 Skill 1건. 실행 워커가 아닌 프롬프트 주입 단위.

    주입 본문(instruction)은 SkillDefinition(skill_builder)에서 가져온다.
    여기서는 연결 메타만 보유한다(중복 데이터 금지).
    """

    agent_id: str
    skill_id: str
    sort_order: int = 0
    created_at: datetime | None = None
