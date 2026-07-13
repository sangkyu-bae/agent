-- knowledge-base-scoping Design §4:
-- 논리 지식베이스 레지스트리. 벡터 격리는 Qdrant/ES payload(kb_id) — 물리 컬렉션과 분리.
-- soft delete(status): 삭제 후 고아 payload 정리(후속 kb-vector-cleanup)를 위해 kb_id 추적 보존.
-- (owner_id, name) 유니크 인덱스는 두지 않는다 — soft-delete 재생성과 충돌 (V037 D4 선례).
--   active 이름 중복 차단은 UseCase가 보장.
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지, DB 기본 상속 (V037 선례).
CREATE TABLE knowledge_base (
    id              VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'kb_id — Qdrant/ES payload 필터 키',
    name            VARCHAR(100) NOT NULL,
    description     VARCHAR(500) NULL,
    owner_id        BIGINT       NOT NULL,
    scope           ENUM('PERSONAL','DEPARTMENT','PUBLIC') NOT NULL DEFAULT 'PERSONAL',
    department_id   VARCHAR(36)  NULL,
    collection_name VARCHAR(100) NOT NULL COMMENT '배정된 물리 Qdrant 컬렉션',
    status          VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active | deleted',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_kb_owner FOREIGN KEY (owner_id) REFERENCES users(id),
    CONSTRAINT fk_kb_department FOREIGN KEY (department_id)
        REFERENCES departments(id) ON DELETE SET NULL,
    INDEX idx_kb_owner_status (owner_id, status),
    INDEX idx_kb_scope_status (scope, status),
    INDEX idx_kb_department (department_id)
) ENGINE=InnoDB;
