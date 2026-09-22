-- approval-gate Design §3.3
-- 에이전트 부작용 도구의 사람 승인 요청 + 런 재개 스냅샷.
-- 시각 규격: 모든 DATETIME 은 UTC naive (agent_schedule·background_job 관례 동일).

CREATE TABLE approval_request (
    id                VARCHAR(36)  NOT NULL COMMENT '승인 요청 ID (uuid4)',
    run_id            VARCHAR(36)  NOT NULL COMMENT '게이트가 발동한 에이전트 런 ID (ai_run 연결)',
    agent_id          VARCHAR(36)  NOT NULL COMMENT '대상 에이전트 ID (agent_definition.id)',
    requested_by      VARCHAR(100) NOT NULL COMMENT '런 실행 신원. 스케줄·웹훅이면 시스템 식별자',
    worker_id         VARCHAR(100) NOT NULL COMMENT '게이트가 걸린 워커 ID. 재개 시 결과 주입 대상',
    tool_id           VARCHAR(200) NOT NULL COMMENT '차단된 도구 ID (tool_catalog.tool_id)',
    tool_args         JSON         NOT NULL COMMENT '차단 시점 도구 인자. 집행 시 그대로 사용',
    draft             LONGTEXT     NOT NULL COMMENT '사람이 검토할 초안 (이메일 본문·변경 내역 등)',
    status            VARCHAR(20)  NOT NULL COMMENT '상태 (pending|approved|scheduled|executed|rejected|expired|failed)',
    idempotency_key   VARCHAR(255) NOT NULL COMMENT '이중 집행 차단 키 (run_id:worker_id:tool_call_id)',
    snapshot_version  INT          NOT NULL DEFAULT 1 COMMENT 'resume_snapshot 포맷 버전. 불일치 시 재개 거부',
    agent_updated_at  DATETIME     NOT NULL COMMENT '적재 시점 agent_definition.updated_at. 재개 전 대조용',
    resume_snapshot   LONGTEXT     NOT NULL COMMENT '워커 진입 시점 SupervisorState 직렬화 JSON (상한 256KB)',
    execute_after     DATETIME     NULL COMMENT '집행 예정 시각(UTC). NULL 이면 승인 즉시 집행',
    expires_at        DATETIME     NOT NULL COMMENT '만료 시각(UTC). 경과 시 expired 로 전이되며 승인 불가',
    decided_by        VARCHAR(100) NULL COMMENT '승인·거절한 사용자 ID',
    decided_at        DATETIME     NULL COMMENT '승인·거절 시각(UTC)',
    decision_reason   TEXT         NULL COMMENT '거절 사유. 재개 시 에이전트에 주입된다',
    executed_at       DATETIME     NULL COMMENT '집행 완료 시각(UTC)',
    error_message     TEXT         NULL COMMENT '집행 실패 사유. 자동 재시도는 하지 않는다',
    seen_at           DATETIME     NULL COMMENT 'NULL=미확인. 벨 배지 기준 (agent_background_job 동형)',
    request_id        VARCHAR(64)  NOT NULL COMMENT '적재 요청의 추적 ID (로그 상관관계)',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각(UTC)',
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각(UTC)',
    PRIMARY KEY (id),
    -- 이중 집행 방어 1차 저지선: 같은 도구 호출로 pending 이 두 번 생기지 않는다.
    UNIQUE KEY uq_approval_request_idempotency (idempotency_key),
    -- 목록 조회: 에이전트별 + 상태 필터
    KEY ix_approval_request_agent_status (agent_id, status),
    -- claim_due 스캔: WHERE status='scheduled' AND execute_after <= now
    KEY ix_approval_request_due (status, execute_after),
    -- 런당 활성 pending 1건 불변식 확인
    KEY ix_approval_request_run (run_id),
    CONSTRAINT fk_approval_request_agent
        FOREIGN KEY (agent_id) REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='에이전트 부작용 도구의 사람 승인 요청 및 런 재개 스냅샷 (approval-gate)';
