-- graph-rag-foundation Design §3.3 (승인 DDL 의 단계 이력 테이블, 번호만 V087 로 앞당김):
-- Flyway outOfOrder=false 에서 모듈 순서대로 적용되도록 만드는 순서로 번호를 매긴다.
-- RAGAS 실행 id 는 소프트 참조(FK 없음). CHARSET/COLLATE 명시 금지. COMMENT 안 콤마 금지.

CREATE TABLE graph_rag_stage_change (
    id                   VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '변경 이력 식별자',
    from_stage           VARCHAR(16)  NOT NULL COMMENT '이전 단계',
    to_stage             VARCHAR(16)  NOT NULL COMMENT '새 단계',
    changed_by           VARCHAR(36)  NOT NULL COMMENT '변경한 관리자 id',
    eval_baseline_run_id VARCHAR(36)  NULL COMMENT '그래프 off RAGAS 실행 id 소프트 참조',
    eval_graph_run_id    VARCHAR(36)  NULL COMMENT '그래프 on RAGAS 실행 id 소프트 참조',
    force_reason         VARCHAR(500) NULL COMMENT '평가 기록 없이 강제 전환한 사유',
    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '변경 시각',
    INDEX idx_grsc_created (created_at)
) ENGINE=InnoDB COMMENT='그래프 RAG 노출 단계 변경 이력';
