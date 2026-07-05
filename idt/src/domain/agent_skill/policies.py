"""agent_skill 도메인 규칙: 부착 검증(SkillAttachPolicy) + 주입 병합(SkillInjectionPolicy).

순수 규칙만 보관 — DB/LLM/외부 호출 없음.
권한(에이전트 수정권한·skill 접근권한)은 application(UseCase)에서 두 도메인 정책을 조합한다.
"""
from dataclasses import dataclass


class SkillAttachPolicy:
    """부착 가능 여부 규칙(중복·최대 개수)."""

    MAX_ATTACHED = 3  # Plan §5.1: 프롬프트 비대화 방지

    @classmethod
    def validate_attach(
        cls, existing_skill_ids: list[str], new_skill_id: str
    ) -> None:
        if new_skill_id in existing_skill_ids:
            raise ValueError("이미 부착된 스킬입니다.")
        if len(existing_skill_ids) >= cls.MAX_ATTACHED:
            raise ValueError(
                f"스킬은 최대 {cls.MAX_ATTACHED}개까지 부착할 수 있습니다."
            )

    @classmethod
    def validate_count(cls, skill_ids: list[str]) -> None:
        """desired-set 일괄 부착 시 개수 상한 검증(agent-skill-toggle).

        중복은 호출부에서 순서보존 dedupe 후 전달한다.
        """
        if len(skill_ids) > cls.MAX_ATTACHED:
            raise ValueError(
                f"스킬은 최대 {cls.MAX_ATTACHED}개까지 부착할 수 있습니다."
            )


@dataclass(frozen=True)
class InjectableSkill:
    """주입에 필요한 최소 정보(skill_builder.SkillDefinition에서 추출)."""

    name: str
    instruction: str
    sort_order: int


class SkillInjectionPolicy:
    """부착 skill instruction → supervisor_prompt 병합 규칙(순수)."""

    MAX_TOTAL_INJECTED = 40_000  # 주입 총 길이 상한(가드). 초과분 skill은 제외.
    BLOCK_HEADER = "[부착된 스킬: {name}]"
    SEPARATOR = "\n\n---\n\n"

    @classmethod
    def merge(cls, base_prompt: str, skills: list[InjectableSkill]) -> str:
        """skills를 sort_order ASC로 base_prompt 앞에 prepend.

        부착 0개(또는 유효 instruction 0개)면 base_prompt를 그대로 반환한다.
        총 주입 길이가 MAX_TOTAL_INJECTED를 넘으면 이후 skill을 제외한다.
        """
        if not skills:
            return base_prompt
        ordered = sorted(skills, key=lambda s: s.sort_order)
        blocks: list[str] = []
        used = 0
        for skill in ordered:
            body = skill.instruction.strip()
            if not body:
                continue
            block = f"{cls.BLOCK_HEADER.format(name=skill.name)}\n{body}"
            if used + len(block) > cls.MAX_TOTAL_INJECTED:
                break
            blocks.append(block)
            used += len(block)
        if not blocks:
            return base_prompt
        return cls.SEPARATOR.join(blocks) + cls.SEPARATOR + base_prompt
