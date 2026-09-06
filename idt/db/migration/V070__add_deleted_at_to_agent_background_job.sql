-- jobs-page-revamp Design §3.3 (FR-01): 작업함에서 끝난 작업을 정리할 수 있도록
-- agent_background_job 에 소프트 삭제 컬럼을 추가한다.
--
-- 물리 삭제를 쓰지 않는 이유: run_id 로 이어지는 ai_run 관측 추적과 감사 이력이
-- 끊긴다. 사용자에게는 사라진 것처럼 보이되 행은 보존한다(복구 UI 는 범위 밖).
--
-- NULL = 활성. 백필하지 않으므로 기존 행은 전부 활성으로 남고, 이 마이그레이션
-- 하나로 동작이 바뀌는 것은 없다(조회 필터는 애플리케이션이 건다).
--
-- 인덱스: 목록·집계 쿼리가 항상 (user_id, deleted_at) 으로 좁힌 뒤 queued_at 으로
-- 정렬하므로 같은 순서의 복합 인덱스를 둔다.
-- 참조: docs/02-design/features/jobs-page-revamp.design.md

ALTER TABLE agent_background_job
    ADD COLUMN deleted_at DATETIME NULL DEFAULT NULL
        COMMENT '소프트 삭제 시각 (UTC). NULL=활성, 값 있으면 목록·집계에서 제외'
        AFTER seen_at;

CREATE INDEX ix_agent_background_job_user_deleted_queued
    ON agent_background_job (user_id, deleted_at, queued_at);
