-- graph-rag-foundation Design §3.3 (승인 DDL 의 판정 기록 테이블, 번호는 만드는 순서로 V089).
-- 엔티티 동일성 판정 기록과 검토 큐. id 는 Neo4j 엣지의 decision_id 와 같다.
-- job·문서·엔티티는 소프트 참조(FK 없음). CHARSET/COLLATE 명시 금지. COMMENT 안 콤마 금지.

CREATE TABLE graph_resolution_decision (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '판정 식별자 — Neo4j 엣지 decision_id와 동일',
    job_id            VARCHAR(36)  NOT NULL COMMENT 'graph_extraction_job.id 소프트 참조',
    document_id       VARCHAR(36)  NOT NULL COMMENT '근거 문서',
    chunk_id          VARCHAR(64)  NOT NULL COMMENT '근거 청크',
    mention_text      VARCHAR(255) NOT NULL COMMENT '언급 원문',
    mention_type      VARCHAR(32)  NOT NULL COMMENT '언급 타입',
    candidates        JSON         NOT NULL COMMENT '후보 목록 라벨 엔티티id 이름 유사도',
    probabilities     JSON         NULL COMMENT 'Jev 라벨별 확률',
    chosen_label      VARCHAR(16)  NOT NULL COMMENT '선택 라벨 C1부터 또는 NEW',
    entity_id         VARCHAR(36)  NOT NULL COMMENT '최종 연결 엔티티 id',
    created_new       TINYINT(1)   NOT NULL COMMENT '새 엔티티 생성 여부',
    decided_by        VARCHAR(16)  NOT NULL COMMENT 'rule 또는 jev 또는 llm_rejudge 또는 llm_fallback',
    band              VARCHAR(16)  NOT NULL COMMENT 'auto_link 또는 auto_new 또는 rejudge 또는 fallback',
    probability       DECIMAL(5,4) NULL COMMENT '판정 확률 — rule은 NULL',
    llm_confidence    VARCHAR(8)   NULL COMMENT 'LLM 판정 자기평가 high 또는 medium 또는 low',
    llm_reason        VARCHAR(500) NULL COMMENT 'LLM 판정 사유 요약',
    review_status     VARCHAR(16)  NOT NULL DEFAULT 'none' COMMENT 'none 또는 pending 또는 approved 또는 rejected',
    reviewed_by       VARCHAR(36)  NULL COMMENT '검토자 id',
    reviewed_at       DATETIME     NULL COMMENT '검토 시각',
    review_note       VARCHAR(500) NULL COMMENT '검토 메모',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    INDEX idx_grd_review (review_status, created_at),
    INDEX idx_grd_document (document_id),
    INDEX idx_grd_entity (entity_id)
) ENGINE=InnoDB COMMENT='엔티티 동일성 판정 기록과 검토 큐';
