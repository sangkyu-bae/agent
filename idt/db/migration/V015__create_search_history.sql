CREATE TABLE search_history (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(100) NOT NULL,
    collection_name VARCHAR(100) NOT NULL,
    document_id     VARCHAR(100) NULL,
    query           TEXT NOT NULL,
    bm25_weight     FLOAT NOT NULL DEFAULT 0.5,
    vector_weight   FLOAT NOT NULL DEFAULT 0.5,
    top_k           INT NOT NULL DEFAULT 10,
    result_count    INT NOT NULL DEFAULT 0,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX ix_sh_user_collection (user_id, collection_name),
    INDEX ix_sh_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
