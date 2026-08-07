-- agent-webhook-outbound D20: outbound 발송 이력 (불변 — INSERT only).
-- COMMENT 문자열에 최상위 콤마 금지 (test_migration_ddl_comments 파서 제약 — M1 함정).
-- FK는 agent_webhook이 아닌 agent_definition 참조 — 채널 삭제/재발급 후에도 이력 보존.
-- FK 참조 테이블은 SQLAlchemy 생성 — CHARSET/COLLATE 명시 금지, ENGINE=InnoDB만 (V037/V056/V057 선례).
CREATE TABLE agent_webhook_delivery (
    id             VARCHAR(36)   NOT NULL COMMENT 'PK (UUID)',
    agent_id       VARCHAR(36)   NOT NULL COMMENT '에이전트 FK (agent_definition.id)',
    run_id         VARCHAR(36)   NULL COMMENT '연계 ai_run id — 실행 관측 조인용 (실행측 미발급 시 NULL)',
    url            VARCHAR(500)  NOT NULL COMMENT '발송 대상 URL (발송 시점 스냅샷 — 이후 변경과 무관)',
    trigger_source VARCHAR(20)   NOT NULL COMMENT '발송 계기 (schedule | webhook)',
    success        TINYINT(1)    NOT NULL COMMENT '최종 성공 여부 (재시도 소진 후 판정)',
    status_code    INT           NULL COMMENT '마지막 응답 HTTP 상태코드 (연결 실패 시 NULL)',
    attempts       INT           NOT NULL COMMENT '총 시도 횟수 (1~4)',
    error          VARCHAR(2000) NULL COMMENT '마지막 오류 메시지 (성공 시 NULL)',
    duration_ms    INT           NOT NULL COMMENT '총 소요 시간 ms (재시도·백오프 포함)',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '기록 시각',
    PRIMARY KEY (id),
    KEY idx_awd_agent_created (agent_id, created_at),
    CONSTRAINT fk_awd_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='웹훅 outbound 발송 이력 — 실패 진단·전송 상태 노출용 (불변 레코드)';
