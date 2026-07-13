-- card-section-summary Design D3/D4: 섹션 요약 백그라운드 잡 (문서당 1행).
-- 섹션별 상태는 저장하지 않음 — 완료 판정은 Qdrant section_summary point 존재(D6).
-- 실행 스냅샷(llm/embedding/profile)으로 실행 중 프로파일 변경에 영향받지 않음.
-- ⚠️ FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지, ENGINE=InnoDB만 (V037 선례).
CREATE TABLE section_summary_job (
    id                  VARCHAR(36)   NOT NULL PRIMARY KEY,
    document_id         VARCHAR(36)   NOT NULL,
    kb_id               VARCHAR(36)   NOT NULL,
    collection_name     VARCHAR(255)  NOT NULL,
    chunking_profile_id VARCHAR(36)   NOT NULL COMMENT '생성 시점 스냅샷',
    llm_model_id        VARCHAR(36)   NOT NULL COMMENT '생성 시점 스냅샷',
    embedding_provider  VARCHAR(50)   NOT NULL COMMENT '원 업로드와 동일 임베딩(차원 일치)',
    embedding_model     VARCHAR(100)  NOT NULL,
    status              VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending|processing|completed|failed',
    total_sections      INT           NULL COMMENT '러너 시작 시 확정',
    done_sections       INT           NOT NULL DEFAULT 0,
    failed_sections     INT           NOT NULL DEFAULT 0,
    error               VARCHAR(1000) NULL,
    created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_summary_job_document (document_id),
    INDEX idx_section_summary_job_kb (kb_id),
    INDEX idx_section_summary_job_status (status)
) ENGINE=InnoDB;
