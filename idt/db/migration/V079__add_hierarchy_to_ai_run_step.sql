-- subagent-step-observability FR-01: 서브에이전트(자식 그래프) step 계층 기록
-- 기존 행은 parent_step_id NULL, depth 0 으로 남아 평면(최상위)으로 해석된다.
-- parent_step_id 에 FK 를 두지 않는다 — 관측 기록은 best-effort 라 부모 기록 실패가
-- 자식 INSERT 실패로 번지면 안 된다 (Design D-03).
ALTER TABLE ai_run_step
    ADD COLUMN parent_step_id VARCHAR(36) NULL COMMENT '감싸는 부모 step id (서브에이전트 wrapper step). 최상위 step은 NULL. FK 없음 - 관측 best-effort',
    ADD COLUMN depth INT NOT NULL DEFAULT 0 COMMENT '중첩 깊이 (0=최상위 그래프, 1=서브에이전트 내부, 2=손자 그래프)';
