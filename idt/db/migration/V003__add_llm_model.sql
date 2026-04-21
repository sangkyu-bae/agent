-- LLM-MODEL-REG-001: llm_model 테이블 신규 생성
-- 지원 LLM 모델을 중앙 관리하기 위한 레지스트리 테이블
-- 참조: docs/02-design/features/llm-model-registry.design.md §3-1

CREATE TABLE llm_model (
    id           VARCHAR(36)  NOT NULL,
    provider     VARCHAR(50)  NOT NULL,
    model_name   VARCHAR(150) NOT NULL,
    display_name VARCHAR(150) NOT NULL,
    description  TEXT         NULL,
    api_key_env  VARCHAR(100) NOT NULL,
    max_tokens   INT          NULL,
    is_active    TINYINT(1)   NOT NULL DEFAULT 1,
    is_default   TINYINT(1)   NOT NULL DEFAULT 0,
    created_at   DATETIME     NOT NULL,
    updated_at   DATETIME     NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_provider_model (provider, model_name),
    INDEX ix_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
