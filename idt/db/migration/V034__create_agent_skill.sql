-- skill-agent-integration Plan §4 / Design §3.3:
-- 에이전트 ↔ Skill 부착(instruction 주입) 조인 테이블. 실행 워커(agent_tool)와 분리.
-- Phase A: instruction만 주입, script_content 실행 없음.
--
-- ⚠️ FK 콜레이션 주의(errno 3780, V037 선례): agent_definition은 SQLAlchemy create_all로
-- 생성되어 DB 기본 콜레이션(utf8mb4_0900_ai_ci)을 사용한다. 테이블 레벨 COLLATE를
-- 명시하지 않아 agent_skill도 DB 기본 콜레이션을 상속 → FK 컬럼 정합.
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
) ENGINE=InnoDB;
