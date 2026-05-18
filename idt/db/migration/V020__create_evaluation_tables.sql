-- RAGAS 평가 모듈 테이블 생성

CREATE TABLE evaluation_run (
    id VARCHAR(36) PRIMARY KEY,
    eval_type VARCHAR(20) NOT NULL COMMENT 'batch | realtime',
    target_type VARCHAR(20) NOT NULL COMMENT 'rag | agent | retrieval',
    target_id VARCHAR(36) NULL COMMENT 'agent_id (Agent 평가 시)',
    status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending | running | completed | failed',
    total_cases INT NOT NULL DEFAULT 0,
    config JSON NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL,
    completed_at DATETIME NULL,
    INDEX idx_eval_run_type (eval_type),
    INDEX idx_eval_run_target (target_type),
    INDEX idx_eval_run_status (status),
    INDEX idx_eval_run_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE evaluation_result (
    id VARCHAR(36) PRIMARY KEY,
    run_id VARCHAR(36) NOT NULL,
    question TEXT NOT NULL,
    ground_truth TEXT NULL,
    answer TEXT NOT NULL,
    contexts JSON NOT NULL,
    metrics JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_eval_result_run FOREIGN KEY (run_id)
        REFERENCES evaluation_run (id) ON DELETE CASCADE,
    INDEX idx_eval_result_run (run_id),
    INDEX idx_eval_result_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE evaluation_testset (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT NULL,
    cases JSON NOT NULL,
    case_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    INDEX idx_testset_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
