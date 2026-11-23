-- document-revision Design §3.3: 개정 판정 로그 (Plan FR-16)
-- 사전 점검·수동 연결·되돌리기마다 신호 점수·LLM 판정·운영자 결정을 남긴다 (auto 임계값 실측용).
-- 문서 FK 없음: 문서 삭제 후에도 로그를 보존한다.
CREATE TABLE document_revision_check (
    id VARCHAR(36) NOT NULL COMMENT 'check_id (uuid4)',
    kb_id VARCHAR(64) NOT NULL COMMENT '대상 KB',
    user_id VARCHAR(128) NOT NULL COMMENT '점검 요청자',
    source VARCHAR(20) NOT NULL COMMENT 'precheck|manual_link|rollback',
    filename VARCHAR(512) NOT NULL COMMENT '새 파일명(수동 연결·되돌리기는 대상 문서 파일명)',
    normalized_name VARCHAR(512) NULL COMMENT '정규화 파일명',
    file_hash CHAR(64) NULL COMMENT '새 파일 SHA-256',
    verdict VARCHAR(30) NOT NULL COMMENT 'new|revision_candidate|duplicate|manual',
    suggested_document_id VARCHAR(64) NULL COMMENT '시스템이 제안한 대상 document_id',
    candidates_json JSON NULL COMMENT '후보별 filename/content/combined 점수·LLM 판정·근거',
    llm_status VARCHAR(10) NOT NULL DEFAULT 'skipped' COMMENT 'ok|failed|skipped',
    elapsed_ms INT NOT NULL DEFAULT 0 COMMENT '점검 소요(ms, 파싱 포함)',
    parse_ms INT NOT NULL DEFAULT 0 COMMENT '파싱 소요(ms) — 파싱 캐시 필요성 판단용',
    decision VARCHAR(20) NULL COMMENT 'revision|new|cancel|rollback_detach|rollback_delete — NULL은 미결정',
    target_document_id VARCHAR(64) NULL COMMENT '운영자가 확정한 대체 대상(구버전) document_id',
    decided_document_id VARCHAR(64) NULL COMMENT '결정으로 생성·변경된 문서 document_id',
    decided_by VARCHAR(128) NULL COMMENT '결정자',
    decided_at DATETIME NULL COMMENT '결정 시각',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    PRIMARY KEY (id),
    INDEX idx_drc_kb_created (kb_id, created_at)
) COMMENT='문서 개정 판정 로그 (document-revision FR-16)';
