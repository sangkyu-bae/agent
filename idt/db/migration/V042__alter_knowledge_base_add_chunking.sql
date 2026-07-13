-- clause-aware-chunking Design §4.2 (additive):
-- use_clause_chunking = opt-in 스위치 (Design D5). NULL 컬럼 = 업로드 시점 late binding:
--   chunking_profile_id NULL → default 프로파일 / chunk_size·chunk_overlap NULL → 프로파일 값.
--   값 존재 → 사용자 오버라이드 고정.
-- FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지 (V037 선례).
ALTER TABLE knowledge_base
    ADD COLUMN use_clause_chunking TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN chunking_profile_id VARCHAR(36) NULL,
    ADD COLUMN chunk_size INT NULL,
    ADD COLUMN chunk_overlap INT NULL,
    ADD CONSTRAINT fk_kb_chunking_profile FOREIGN KEY (chunking_profile_id)
        REFERENCES chunking_profile(id);
