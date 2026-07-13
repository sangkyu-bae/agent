-- kb-management-ui D1: 논리 지식베이스 문서 목록용 kb_id 컬럼 (additive, NULL 허용)
-- 일반 업로드 문서는 NULL — 기존 동작 불변.
-- FK 미설정: KB soft-delete와 독립 (V037 주석 선례: CHARSET/COLLATE 명시 금지)
ALTER TABLE document_metadata
    ADD COLUMN kb_id VARCHAR(64) NULL DEFAULT NULL,
    ADD INDEX idx_dm_kb (kb_id);
