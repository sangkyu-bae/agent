-- V013: collection_permissions 테이블 생성
-- 컬렉션별 권한(PERSONAL/DEPARTMENT/PUBLIC) 관리

CREATE TABLE IF NOT EXISTS collection_permissions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    owner_id        BIGINT NOT NULL,
    scope           ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id   VARCHAR(36) NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_perm_collection_name (collection_name),
    INDEX ix_perm_owner (owner_id),
    INDEX ix_perm_department (department_id),
    INDEX ix_perm_scope (scope),

    CONSTRAINT fk_perm_user FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_perm_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
