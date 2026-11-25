-- firewall-agent Design §3.3: 에이전트 알림(Alertmanager 웹훅) 수신 (Plan FR-10~14)
-- 수신 설정은 에이전트당 1개, 토큰은 sha256 해시만 저장한다. 수신 이력은 결과와 중복 판정 근거를 남긴다.
-- additive 변경 (신규 테이블 2개). 에이전트 삭제 시 설정·이력 함께 삭제.
CREATE TABLE agent_alert_receiver (
    id VARCHAR(36) NOT NULL COMMENT '수신 설정 ID',
    agent_id VARCHAR(36) NOT NULL COMMENT '대상 에이전트 (에이전트당 1개)',
    user_id VARCHAR(100) NOT NULL COMMENT '설정자 = 실행 신원',
    enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '수신 켜짐 여부',
    skip_when_busy TINYINT(1) NOT NULL DEFAULT 1 COMMENT '진행 중·승인 대기 건이 있으면 실행하지 않음',
    token_hash VARCHAR(64) NOT NULL COMMENT 'Bearer 토큰 sha256 hex',
    token_hint VARCHAR(8) NOT NULL COMMENT '토큰 끝 4자 (식별용)',
    instruction_prefix VARCHAR(300) NOT NULL DEFAULT '' COMMENT '지침문 맨 앞에 붙일 문구',
    created_at DATETIME NOT NULL COMMENT '생성 시각 (UTC)',
    updated_at DATETIME NOT NULL COMMENT '수정 시각 (UTC)',
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_alert_receiver_agent (agent_id),
    CONSTRAINT fk_agent_alert_receiver_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='에이전트별 알림(Alertmanager 웹훅) 수신 설정';

CREATE TABLE agent_alert_receipt (
    id VARCHAR(36) NOT NULL COMMENT '수신 ID',
    receiver_id VARCHAR(36) NOT NULL COMMENT '수신 설정 ID',
    agent_id VARCHAR(36) NOT NULL COMMENT '대상 에이전트 (비정규화)',
    group_key_hash VARCHAR(64) NOT NULL COMMENT 'groupKey sha256 hex',
    fingerprints_hash VARCHAR(64) NOT NULL COMMENT '발화 알림 fingerprint 집합 sha256 hex',
    firing_count INT NOT NULL COMMENT '발화 알림 수',
    result VARCHAR(16) NOT NULL COMMENT 'enqueued|duplicate|resolved_only|disabled|skipped_busy|invalid_payload',
    skip_reason VARCHAR(32) NULL COMMENT 'skipped_busy 사유',
    job_id VARCHAR(36) NULL COMMENT '등록된 백그라운드 잡 ID',
    received_at DATETIME NOT NULL COMMENT '수신 시각 (UTC)',
    request_id VARCHAR(64) NOT NULL COMMENT '요청 추적 ID',
    PRIMARY KEY (id),
    KEY ix_agent_alert_receipt_dedupe (receiver_id, group_key_hash, received_at),
    CONSTRAINT fk_agent_alert_receipt_receiver FOREIGN KEY (receiver_id)
        REFERENCES agent_alert_receiver (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='알림 수신 이력 (결과·중복 판정 근거)';
