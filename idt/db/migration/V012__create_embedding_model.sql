CREATE TABLE embedding_model (
    id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
    provider        VARCHAR(50)  NOT NULL,
    model_name      VARCHAR(100) NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    vector_dimension INT         NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    description     TEXT         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_model_name (model_name),
    INDEX ix_provider (provider),
    INDEX ix_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO embedding_model (provider, model_name, display_name, vector_dimension, description) VALUES
('openai', 'text-embedding-3-small', 'OpenAI Embedding 3 Small', 1536, '가성비 좋은 범용 임베딩 모델'),
('openai', 'text-embedding-3-large', 'OpenAI Embedding 3 Large', 3072, '고품질 임베딩 모델 (정확도 우선)'),
('openai', 'text-embedding-ada-002', 'OpenAI Ada 002', 1536, '이전 세대 범용 임베딩 모델');
