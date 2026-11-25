-- firewall-agent Design §3.3: 스케줄 자동 실행 건너뜀 옵션 (Plan FR-06·07)
-- 같은 에이전트에 승인 대기·진행 중 실행이 있으면 회차를 실행하지 않고 skipped 이력만 남긴다.
-- additive 변경. 기본값 0(off)이라 기존 스케줄 동작은 바뀌지 않는다.
-- agent_schedule_run.status 는 VARCHAR(10) 이라 'skipped' 를 그대로 담는다 (컬럼 변경 없음).
ALTER TABLE agent_schedule
    ADD COLUMN skip_when_busy TINYINT(1) NOT NULL DEFAULT 0 COMMENT '진행 중·승인 대기 건이 있으면 회차 건너뜀';

ALTER TABLE agent_schedule_run
    ADD COLUMN skip_reason VARCHAR(32) NULL COMMENT 'status=skipped 사유 (approval_pending|run_in_progress|check_failed)';
