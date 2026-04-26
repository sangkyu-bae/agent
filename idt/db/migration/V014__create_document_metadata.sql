CREATE TABLE IF NOT EXISTS document_metadata (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    document_id     VARCHAR(64)  NOT NULL,
    collection_name VARCHAR(128) NOT NULL,
    filename        VARCHAR(512) NOT NULL,
    category        VARCHAR(128) NOT NULL DEFAULT 'uncategorized',
    user_id         VARCHAR(128) NOT NULL DEFAULT '',
    chunk_count     INT          NOT NULL DEFAULT 0,
    chunk_strategy  VARCHAR(64)  NOT NULL DEFAULT 'unknown',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_document_id (document_id),
    INDEX idx_dm_collection (collection_name),
    INDEX idx_dm_user (user_id),
    INDEX idx_dm_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
