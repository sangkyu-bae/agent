-- document-revision Design §3.3: KB별 개정 판정 모드 (Plan FR-15). auto 는 후속 사이클.
ALTER TABLE knowledge_base
    ADD COLUMN revision_mode VARCHAR(10) NOT NULL DEFAULT 'suggest' COMMENT '개정 판정 모드 suggest|auto (auto는 후속 사이클)';
