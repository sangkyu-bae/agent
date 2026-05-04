-- V017__add_agent_subscription_and_fork.sql
-- 에이전트 구독(북마크) + 포크(전체 복사 커스터마이징) 지원

-- 1. agent_definition에 포크 관련 컬럼 추가
ALTER TABLE agent_definition
    ADD COLUMN forked_from VARCHAR(36) NULL AFTER temperature,
    ADD COLUMN forked_at DATETIME NULL AFTER forked_from;

ALTER TABLE agent_definition
    ADD INDEX ix_agent_forked_from (forked_from);

-- 2. 구독 테이블 생성
-- NOTE: user_id는 VARCHAR(100)로 agent_definition과 동일 패턴 (users.id는 INT이므로 FK 미설정)
CREATE TABLE user_agent_subscription (
    id VARCHAR(36) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    agent_id VARCHAR(36) NOT NULL,
    is_pinned TINYINT(1) NOT NULL DEFAULT 0,
    subscribed_at DATETIME NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_user_agent_sub (user_id, agent_id),
    INDEX ix_subscription_user (user_id),
    INDEX ix_subscription_agent (agent_id),

    CONSTRAINT fk_sub_agent FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
