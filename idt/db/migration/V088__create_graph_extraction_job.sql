-- graph-rag-foundation Design §3.3 (승인 DDL 의 추출 잡 테이블, 번호는 만드는 순서로 V088).
-- 문서 단위 그래프 추출 실행 이력. document_id·kb_id 는 소프트 참조(FK 없음).
-- CHARSET/COLLATE 명시 금지. COMMENT 안 콤마 금지.

CREATE TABLE graph_extraction_job (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '잡 식별자',
    document_id       VARCHAR(36)  NOT NULL COMMENT 'document_metadata.document_id 소프트 참조',
    kb_id             VARCHAR(36)  NULL COMMENT 'knowledge_base.id 소프트 참조',
    collection_name   VARCHAR(255) NOT NULL COMMENT '청크가 저장된 컬렉션',
    status            VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending 또는 processing 또는 completed 또는 partial 또는 failed',
    mode              VARCHAR(16)  NOT NULL DEFAULT 'resume' COMMENT 'resume 완료 청크 건너뜀 또는 rebuild 문서 그래프 삭제 후 재추출',
    trigger_source    VARCHAR(16)  NOT NULL COMMENT 'upload 자동 또는 admin 수동',
    extractor_version VARCHAR(16)  NOT NULL COMMENT '추출기 버전 — 바뀌면 resume도 재추출',
    total_chunks      INT          NOT NULL DEFAULT 0 COMMENT '대상 청크 수',
    processed_chunks  INT          NOT NULL DEFAULT 0 COMMENT '처리 완료 청크 수',
    failed_chunks     INT          NOT NULL DEFAULT 0 COMMENT '처리 실패 청크 수',
    llm_calls         INT          NOT NULL DEFAULT 0 COMMENT '추출과 판정 LLM 호출 합계',
    judge_calls       INT          NOT NULL DEFAULT 0 COMMENT 'Jev 호출 수',
    entities_created  INT          NOT NULL DEFAULT 0 COMMENT '새로 만든 엔티티 수',
    entities_linked   INT          NOT NULL DEFAULT 0 COMMENT '기존 엔티티에 연결한 언급 수',
    relations_created INT          NOT NULL DEFAULT 0 COMMENT '저장한 관계 엣지 수',
    error_message     TEXT         NULL COMMENT '실패 사유 요약',
    requested_by      VARCHAR(36)  NULL COMMENT '요청 사용자 id 소프트 참조',
    started_at        DATETIME     NULL COMMENT '처리 시작 시각',
    finished_at       DATETIME     NULL COMMENT '처리 종료 시각',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    INDEX idx_gej_document (document_id, created_at),
    INDEX idx_gej_status (status)
) ENGINE=InnoDB COMMENT='그래프 추출 잡 — 문서 단위 실행 이력';
