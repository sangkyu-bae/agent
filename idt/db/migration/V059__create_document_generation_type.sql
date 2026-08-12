-- doc-generator Design §3:
-- 문서생성기 문서 유형 — 에이전트·워커 전용 아웃라인 정의.
-- (agent_id, worker_id) 유니크 인덱스는 두지 않는다 — soft-delete 재등록과 충돌
-- (V037 document_template D4 선례). "도구당 active 유형 1개"는 저장 UseCase가 보장.
-- mcp_html_to_doc_tool_id·type_id는 워커 tool_config에 저장(추출기 동형) — 테이블은 유형 본문만.
--
-- ⚠️ FK 콜레이션 주의(errno 3780): agent_definition은 SQLAlchemy create_all로 생성되어
-- DB 기본 콜레이션을 사용한다. 테이블 레벨 CHARSET/COLLATE를 명시하지 않아
-- document_generation_type도 동일한 DB 기본 콜레이션을 상속 → FK 컬럼 정합.
CREATE TABLE document_generation_type (
    id            VARCHAR(36)  NOT NULL COMMENT '문서 유형 ID (UUID)',
    agent_id      VARCHAR(36)  NOT NULL COMMENT '소유 에이전트 ID (agent_definition FK)',
    worker_id     VARCHAR(100) NOT NULL COMMENT '대상 워커 ID (document_generator 도구 워커)',
    name          VARCHAR(100) NOT NULL COMMENT '문서 유형명 (산출 파일명·프롬프트에 사용)',
    description   VARCHAR(500) NOT NULL DEFAULT '' COMMENT '문서 용도 설명 (작성 프롬프트에 주입)',
    sections      JSON         NOT NULL COMMENT '섹션 아웃라인 (title·guidance 객체 배열 — 순서 보존)',
    output_format VARCHAR(8)   NOT NULL DEFAULT 'docx' COMMENT '출력 포맷 (pdf|docx, 기본 docx — D4)',
    status        VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT '상태 (active|deleted, soft-delete)',
    created_at    DATETIME     NOT NULL COMMENT '생성 시각 (UTC)',
    updated_at    DATETIME     NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id),
    INDEX idx_document_generation_type_agent_worker (agent_id, worker_id, status),
    CONSTRAINT fk_document_generation_type_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='문서생성기 문서 유형 — 에이전트·워커 전용 아웃라인 정의 (doc-generator)';
