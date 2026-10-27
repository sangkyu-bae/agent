-- agent-opener Design §3.3:
--   에이전트별 대화 시작 예시 질문(오프너). 순서는 sort_order(배열 인덱스). 저장은 전체 교체.
--   agent_definition 삭제는 소프트(status=deleted)라 CASCADE 는 하드 삭제 대비용.
--
-- ⚠️ FK 콜레이션 주의(errno 3780, V034/V037 선례): agent_definition 은 SQLAlchemy create_all 로
--   생성되어 DB 기본 콜레이션을 쓴다. 테이블 레벨 COLLATE 를 명시하지 않아 상속시킨다.
-- ⚠️ COMMENT 안에 최상위 콤마 금지 (tests/db/test_migration_ddl_comments.py 파서).
CREATE TABLE agent_opener (
    id          VARCHAR(36)  NOT NULL COMMENT 'UUID PK',
    agent_id    VARCHAR(36)  NOT NULL COMMENT 'agent_definition.id (CASCADE)',
    text        VARCHAR(200) NOT NULL COMMENT '예시 질문 본문(strip 완료)',
    sort_order  INT          NOT NULL DEFAULT 0 COMMENT '표시 순서(작을수록 먼저)',
    created_at  DATETIME     NOT NULL COMMENT '생성 시각(UTC)',
    PRIMARY KEY (id),
    CONSTRAINT fk_agent_opener_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition(id) ON DELETE CASCADE,
    INDEX ix_agent_opener_agent (agent_id)
) ENGINE=InnoDB COMMENT='에이전트별 대화 시작 예시 질문(오프너)';
