-- retrieval-observability Design §3.1 (D5~D7/D9): 검색 실행 쿼리·모드·개별 점수 기록.
-- 전 컬럼 nullable additive — 기존 데이터/기록 코드 하위호환.
ALTER TABLE ai_retrieval_source
    ADD COLUMN search_query  TEXT           NULL COMMENT '검색 엔진에 실제 투입된 쿼리(재작성 포함)',
    ADD COLUMN query_source  VARCHAR(20)    NULL COMMENT 'original | multi_query',
    ADD COLUMN search_mode   VARCHAR(20)    NULL COMMENT 'hybrid | bm25_only | vector_only | routed',
    ADD COLUMN bm25_score    DECIMAL(10, 6) NULL COMMENT 'RRF 병합 전 BM25 원점수',
    ADD COLUMN vector_score  DECIMAL(10, 6) NULL COMMENT 'RRF 병합 전 벡터 코사인 점수',
    ADD COLUMN bm25_rank     INT            NULL,
    ADD COLUMN vector_rank   INT            NULL,
    ADD COLUMN fusion_source VARCHAR(20)    NULL COMMENT 'both | bm25_only | vector_only';
