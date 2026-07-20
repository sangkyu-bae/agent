-- kb-retrieval-test D6: KB 단위 검색 히스토리 — additive nullable 컬럼
-- 기존 행/컬렉션 검색 경로는 kb_id NULL로 무영향
ALTER TABLE search_history
    ADD COLUMN kb_id VARCHAR(64) NULL,
    ADD INDEX ix_sh_user_kb (user_id, kb_id);
