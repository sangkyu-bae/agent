CREATE TABLE IF NOT EXISTS collection_activity_log (
    id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    action          VARCHAR(30)  NOT NULL,
    user_id         VARCHAR(100) NULL,
    detail          JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_cal_collection (collection_name),
    INDEX ix_cal_action (action),
    INDEX ix_cal_created_at (created_at),
    INDEX ix_cal_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
