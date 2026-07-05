-- document-template-extractor Design §2-4:
-- 에이전트·도구 전용 문서 템플릿 (공유/fork/visibility 없음 — Plan 관심사 분리 ②).
-- (agent_id, worker_id) 유니크 인덱스는 두지 않는다(D4) — soft-delete 재등록과 충돌.
-- "도구당 active 템플릿 1개"는 저장 UseCase가 보장(기존 active soft-delete 후 insert).
--
-- ⚠️ FK 콜레이션 주의(errno 3780): agent_definition은 SQLAlchemy create_all로 생성되어
-- DB 기본 콜레이션(MySQL 8: utf8mb4_0900_ai_ci 등)을 사용한다. 테이블 레벨 COLLATE를
-- 명시하지 않아 document_template도 동일한 DB 기본 콜레이션을 상속 → FK 컬럼 정합.
-- (agent_id는 반드시 agent_definition.id와 같은 charset/collation이어야 함.)
CREATE TABLE document_template (
    id              VARCHAR(36)  NOT NULL PRIMARY KEY,
    agent_id        VARCHAR(36)  NOT NULL,
    worker_id       VARCHAR(100) NOT NULL COMMENT '예: document_extractor_worker',
    name            VARCHAR(200) NOT NULL,
    html_skeleton   LONGTEXT     NOT NULL COMMENT '{{key}} 토큰화된 HTML (방식 A)',
    slots           JSON         NOT NULL COMMENT 'TemplateSlot 배열 통째 저장',
    source_file_ref VARCHAR(500) NOT NULL COMMENT '원본 영구 보관 경로 (D3)',
    source_format   VARCHAR(10)  NOT NULL COMMENT 'pdf | docx',
    status          VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active | deleted',
    created_at      DATETIME     NOT NULL,
    updated_at      DATETIME     NOT NULL,
    CONSTRAINT fk_document_template_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    INDEX idx_document_template_agent_worker (agent_id, worker_id, status)
) ENGINE=InnoDB;
