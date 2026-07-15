-- kb-custom-chunking Design D1 (additive):
-- use_custom_chunking = 독립 opt-in 스위치. 조항 청킹(use_clause_chunking)과
--   상호배타(앱 레이어 검증 V-07) — 기존 조항 컬럼 4개의 의미는 불변.
-- custom_chunking_config = 전략/파라미터/경계규칙 JSON (version 키 포함, Design §4.1).
-- FK 없음 — 콜레이션 이슈(errno 3780) 해당 없음.
ALTER TABLE knowledge_base
    ADD COLUMN use_custom_chunking TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN custom_chunking_config JSON NULL;
