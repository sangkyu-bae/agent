-- skill-agent-integration Plan §4 / Design §3.3:
-- 에이전트 ↔ Skill 부착(instruction 주입) 조인 테이블. 실행 워커(agent_tool)와 분리.
-- Phase A: instruction만 주입, script_content 실행 없음.
CREATE TABLE agent_skill (
    id          VARCHAR(36)  PRIMARY KEY,
    agent_id    VARCHAR(36)  NOT NULL,
    skill_id    VARCHAR(36)  NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 0 COMMENT '주입 순서(작을수록 먼저)',
    created_at  DATETIME     NOT NULL,
    CONSTRAINT fk_agent_skill_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_skill_skill FOREIGN KEY (skill_id)
        REFERENCES skill_definition(id) ON DELETE CASCADE,
    CONSTRAINT uq_agent_skill UNIQUE (agent_id, skill_id),
    INDEX ix_agent_skill_agent (agent_id),
    INDEX ix_agent_skill_skill (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
