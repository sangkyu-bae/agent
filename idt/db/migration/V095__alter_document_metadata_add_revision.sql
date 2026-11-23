-- document-revision Design §3.3: 문서 개정 계보·상태 (additive, 기존 행은 v1·active·synced)
-- 상태의 원본은 이 테이블이며, 청크 payload revision_status 는 검색 제외용 사본이다.
-- Flyway 순서: V093·V094(answer-citation-verification) 다음. 머지 순서 확인 필요.
ALTER TABLE document_metadata
    ADD COLUMN file_hash CHAR(64) NULL COMMENT '원본 파일 SHA-256 (document-revision). 기존 행 NULL',
    ADD COLUMN lineage_id VARCHAR(64) NULL COMMENT '개정 계보 ID. NULL이면 자기 document_id가 계보 ID',
    ADD COLUMN version_no INT NOT NULL DEFAULT 1 COMMENT '계보 내 버전 번호(1부터)',
    ADD COLUMN version_label VARCHAR(100) NULL COMMENT '운영자 입력 버전 라벨(예: 2026-11 개정)',
    ADD COLUMN effective_date DATE NULL COMMENT '시행일(표시용, 전환 시점에 영향 없음)',
    ADD COLUMN revision_status VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active|superseded — 검색 제외 원본',
    ADD COLUMN sync_state VARCHAR(20) NOT NULL DEFAULT 'synced' COMMENT 'synced|pending — 청크 payload 표식 반영 여부',
    ADD COLUMN superseded_by VARCHAR(64) NULL COMMENT '이 문서를 대체한 document_id(감사용)',
    ADD COLUMN superseded_at DATETIME NULL COMMENT '대체 확정 시각',
    ADD COLUMN revised_by VARCHAR(128) NULL COMMENT '개정 확정·연결을 수행한 사용자 ID',
    ADD INDEX idx_dm_kb_hash (kb_id, file_hash),
    ADD INDEX idx_dm_lineage (lineage_id, version_no),
    ADD INDEX idx_dm_kb_status (kb_id, revision_status);
