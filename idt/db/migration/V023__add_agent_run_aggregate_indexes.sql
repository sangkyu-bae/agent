-- V023: ai_llm_call.created_at 단독 인덱스 추가 (M5 / AGENT-OBS-005)
--
-- 배경:
--   M4에서 노출된 집계 API (by-user / by-llm / by-node)가 모두
--   WHERE created_at BETWEEN :from AND :to 형태로 날짜 범위 스캔을 수행한다.
--   V021의 기존 composite 인덱스들은 leading column이 (user_id, ...) / (llm_model_id, ...)이라
--   필터에 leading column이 없으면 인덱스를 활용할 수 없다.
--
-- 목적:
--   ai_llm_call.created_at 단독 인덱스로 날짜 범위 스캔을 가속 → 데이터 누적 시 슬로우 방지.
--
-- 참고:
--   - ai_llm_call.step_id는 V021 fk_llm_call_step FOREIGN KEY가 InnoDB 자동 인덱스 생성으로 이미 커버됨
--     (별도 idx_llm_call_step 추가는 본 마이그레이션에서 제외 — 운영 EXPLAIN 결과 따라 V024로 별도)
--   - ai_run.started_at은 V021 idx_run_started_at으로 이미 존재 (list_runs ORDER BY 자동 가속)
--
-- 운영 적용:
--   본 마이그레이션은 dev/test 환경 검증용. 운영 적용은 유지보수 윈도우에서 별도 절차로 진행한다.
--   InnoDB 5.6+ online DDL (LOCK=NONE) 가능 여부 확인 후 락 영향 최소화.

ALTER TABLE ai_llm_call
ADD INDEX idx_llm_call_created (created_at);
