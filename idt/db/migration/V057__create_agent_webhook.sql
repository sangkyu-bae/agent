-- agent-webhook Design §3: 에이전트별 웹훅 채널 (1:1, opt-in).
-- 시크릿은 평문 저장 (D2 — HMAC 서명 재계산에 원문 필요, 해시 저장과 양립 불가.
-- MCP 레지스트리 api_key 보관(V032)과 동급 수준, 유출 시 rotate 대응).
-- FK 참조 테이블(agent_definition)은 SQLAlchemy 생성 — CHARSET/COLLATE 명시 금지,
-- ENGINE=InnoDB만 지정 (MySQL errno 3780 선례, V037/V056 주석 참조).
CREATE TABLE agent_webhook (
    id               VARCHAR(36)  NOT NULL COMMENT 'PK (UUID)',
    agent_id         VARCHAR(36)  NOT NULL COMMENT '에이전트 FK (agent_definition.id) — 에이전트당 1채널',
    enabled          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT 'inbound 수신 활성 여부 — false면 호출 404',
    secret           VARCHAR(64)  NOT NULL COMMENT '시크릿 원문 — HMAC 서명 재계산용 (D2). 조회 응답·로그 노출 금지 (hint만 노출)',
    secret_hint      VARCHAR(8)   NOT NULL COMMENT '시크릿 끝 4자 — UI 식별용 표시',
    outbound_url     VARCHAR(500) NULL COMMENT 'outbound 발송 대상 URL (M2, http/https만) — NULL이면 미등록',
    outbound_enabled TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'outbound 발송 활성 여부 (M2)',
    created_by       VARCHAR(36)  NOT NULL COMMENT '채널 생성자 user_id (감사용)',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_webhook_agent (agent_id),
    CONSTRAINT fk_agent_webhook_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='에이전트 웹훅 채널 — 외부 시스템 inbound 호출 인증(시크릿)과 outbound 발송 설정 (소유자 opt-in)';
