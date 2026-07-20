-- agent-memory Phase 1: 사용자 수동 메모리. Phase 2/3 확장 컬럼(scope/tier/status/
-- source_run_id/confidence/expires_at) 선반영.
-- FK/COLLATE 명시 없음 (V037 주석 선례), ENGINE=InnoDB.
CREATE TABLE agent_memory (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope         VARCHAR(10)  NOT NULL DEFAULT 'user'   COMMENT 'user|org (Phase1은 user 고정)',
    user_id       VARCHAR(255) NULL                      COMMENT 'scope=user일 때 소유자',
    tier          TINYINT      NOT NULL DEFAULT 0        COMMENT '0=상주 주입, 1=온디맨드(Phase3)',
    mem_type      VARCHAR(20)  NOT NULL                  COMMENT 'profile|preference|domain_term|episode',
    content       VARCHAR(500) NOT NULL,
    source_run_id VARCHAR(64)  NULL                      COMMENT '자동 추출 출처(Phase2) — Phase1은 NULL',
    confidence    TINYINT      NOT NULL DEFAULT 100      COMMENT '수동 입력=100',
    status        VARCHAR(10)  NOT NULL DEFAULT 'active' COMMENT 'pending|active|rejected|expired',
    expires_at    DATETIME     NULL,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    INDEX idx_memory_user_status (user_id, status)
) ENGINE=InnoDB;
