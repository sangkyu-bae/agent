-- agent-schedule: 에이전트 스케줄 정의 + 실행 이력
-- Design: docs/02-design/features/agent-schedule.design.md §7
-- 포크 미복사(R5): 스케줄은 agent_definition 컬럼이 아닌 본 별도 테이블에만 존재.
--
-- ⚠️ FK 콜레이션 주의(errno 3780, V037 선례): agent_definition은 SQLAlchemy
-- create_all로 생성되어 DB 기본 콜레이션(MySQL 8: utf8mb4_0900_ai_ci 등)을 사용한다.
-- 테이블 레벨 CHARSET/COLLATE를 명시하지 않아 동일한 DB 기본값을 상속 → FK 컬럼 정합.

CREATE TABLE agent_schedule (
  id            VARCHAR(36) PRIMARY KEY,
  agent_id      VARCHAR(36) NOT NULL,
  user_id       VARCHAR(100) NOT NULL,
  name          VARCHAR(200) NOT NULL,
  schedule_type VARCHAR(10)  NOT NULL,          -- once|daily|weekly|cron
  run_date      DATE NULL,                      -- once 전용
  time_of_day   TIME NULL,                      -- once/daily/weekly 전용
  days_of_week  JSON NULL,                      -- weekly 전용, [0,2,4] (0=월..6=일)
  cron_expr     VARCHAR(100) NULL,              -- cron 전용
  instruction   TEXT NOT NULL,                  -- R9: 지침 (실행 시 변수 치환 -> user 질문)
  enabled       TINYINT(1) NOT NULL DEFAULT 1,
  timezone      VARCHAR(50) NOT NULL DEFAULT 'Asia/Seoul',
  next_run_at   DATETIME NULL,                  -- UTC. due 판정 키
  last_run_at   DATETIME NULL,
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL,
  CONSTRAINT fk_agent_schedule_agent
    FOREIGN KEY (agent_id) REFERENCES agent_definition(id) ON DELETE CASCADE,
  INDEX idx_agent_schedule_due (enabled, next_run_at),
  INDEX idx_agent_schedule_agent (agent_id)
) ENGINE=InnoDB;

CREATE TABLE agent_schedule_run (
  id            VARCHAR(36) PRIMARY KEY,
  schedule_id   VARCHAR(36) NOT NULL,
  agent_id      VARCHAR(36) NOT NULL,           -- 스케줄 삭제 후 이력 추적용 비정규화
  status        VARCHAR(10) NOT NULL,           -- running|success|failed
  scheduled_for DATETIME NOT NULL,              -- 원래 예정 시각 (UTC)
  started_at    DATETIME NOT NULL,
  finished_at   DATETIME NULL,
  session_id    VARCHAR(36) NULL,               -- 생성된 대화 세션
  run_id        VARCHAR(36) NULL,               -- ai_run 연결 (AGENT-OBS-001)
  error_message TEXT NULL,
  request_id    VARCHAR(64) NOT NULL,
  CONSTRAINT fk_schedule_run_schedule
    FOREIGN KEY (schedule_id) REFERENCES agent_schedule(id) ON DELETE CASCADE,
  INDEX idx_schedule_run_schedule (schedule_id, started_at),
  INDEX idx_schedule_run_agent (agent_id, started_at)
) ENGINE=InnoDB;
