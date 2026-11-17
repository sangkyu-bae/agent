-- graph-rag-foundation Design §11.9 (module-4b 주제 분류, 2026-11-17 사용자 승인 DDL).
-- 문서 ↔ 주제 연결. 대표(대분류+소분류)는 is_primary=1, 보조 대분류는 0.
-- document_id·topic_id·decision_id 는 소프트 참조(FK 없음).
-- CHARSET/COLLATE 명시 금지. COMMENT 안 콤마 금지.

CREATE TABLE graph_document_topic (
    document_id       VARCHAR(36)  NOT NULL COMMENT '문서 id 소프트 참조',
    topic_id          VARCHAR(36)  NOT NULL COMMENT 'graph_topic.id 소프트 참조',
    is_primary        TINYINT(1)   NOT NULL COMMENT '대표 주제 여부',
    probability       DECIMAL(5,4) NULL COMMENT '판정 확률 — rule과 LLM은 NULL',
    decision_id       VARCHAR(36)  NOT NULL COMMENT 'graph_resolution_decision.id 소프트 참조',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    PRIMARY KEY (document_id, topic_id),
    INDEX idx_gdt_topic (topic_id)
) ENGINE=InnoDB COMMENT='문서와 주제 연결 — 그래프 검색 범위';
