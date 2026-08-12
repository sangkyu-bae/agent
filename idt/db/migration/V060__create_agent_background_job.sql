-- background-jobs: ad-hoc 백그라운드 작업 큐 + 이력
-- Design: docs/02-design/features/background-jobs.design.md §3
-- ⚠️ FK 콜레이션 주의(errno 3780, V037/V038 선례): 테이블 레벨 CHARSET/COLLATE
-- 미명시로 DB 기본값 상속 → agent_definition FK 컬럼 정합. ENGINE=InnoDB만 명시.

CREATE TABLE agent_background_job (
  id            VARCHAR(36)  PRIMARY KEY                COMMENT '작업 ID (uuid4)',
  user_id       VARCHAR(100) NOT NULL                   COMMENT '등록 사용자 ID (실행 신원·조회 인가 기준)',
  agent_id      VARCHAR(36)  NOT NULL                   COMMENT '실행 대상 에이전트 ID',
  source        VARCHAR(10)  NOT NULL DEFAULT 'chat'    COMMENT '등록 경로 (chat|api)',
  query         TEXT         NOT NULL                   COMMENT '실행할 사용자 질문',
  session_id    VARCHAR(36)  NULL                       COMMENT '대화 세션 ID (미지정 시 실행 시 생성 후 역기입)',
  run_id        VARCHAR(36)  NULL                       COMMENT 'ai_run 연결 (AGENT-OBS-001)',
  status        VARCHAR(10)  NOT NULL DEFAULT 'queued'  COMMENT '상태 (queued|running|success|failed)',
  error_message TEXT         NULL                       COMMENT '실패 사유 (2000자 절단)',
  seen_at       DATETIME     NULL                       COMMENT '사용자 결과 확인 시각 (NULL=미확인, 벨 배지 집계 기준)',
  queued_at     DATETIME     NOT NULL                   COMMENT '등록 시각 (UTC, claim 순서 기준)',
  started_at    DATETIME     NULL                       COMMENT '실행 시작 시각 (UTC)',
  finished_at   DATETIME     NULL                       COMMENT '실행 종료 시각 (UTC)',
  request_id    VARCHAR(64)  NOT NULL                   COMMENT '등록 요청 추적 ID',
  created_at    DATETIME     NOT NULL                   COMMENT '생성 시각 (UTC)',
  updated_at    DATETIME     NOT NULL                   COMMENT '수정 시각 (UTC)',
  CONSTRAINT fk_bg_job_agent
    FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE,
  INDEX idx_bg_job_claim (status, queued_at),
  INDEX idx_bg_job_user (user_id, queued_at),
  INDEX idx_bg_job_unseen (user_id, seen_at, status)
) ENGINE=InnoDB COMMENT='ad-hoc 백그라운드 작업 큐·이력 (background-jobs)';
