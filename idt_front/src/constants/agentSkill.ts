/**
 * agent-skill-toggle 상수.
 *
 * 에이전트 1개에 부착 가능한 최대 스킬 개수.
 * 백엔드 `SkillAttachPolicy.MAX_ATTACHED`(idt/src/domain/agent_skill/policies.py)와
 * 반드시 동기화한다 — 값 변경 시 양쪽을 함께 수정.
 */
export const MAX_ATTACHED_SKILLS = 3;
