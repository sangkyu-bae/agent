-- agent-model-benchmark Design §3.3: evaluation_run에 모델 차원을,
-- evaluation_result에 관측 연결 키와 도구 호출 기록을 추가한다.
-- 신규 컬럼은 전부 nullable — 기존 row와 기존 조회 경로에 영향이 없다.
-- 참조: docs/02-design/features/agent-model-benchmark.design.md

ALTER TABLE evaluation_run
    ADD COLUMN sweep_id VARCHAR(36) NULL
        COMMENT '소속 스윕 ID — NULL이면 단독 실행(기존 배치 평가)' AFTER target_id,
    ADD COLUMN llm_model_id VARCHAR(36) NULL
        COMMENT '이 run에서 사용한 피평가 LLM 모델 ID — 모델 비교의 축' AFTER sweep_id,
    ADD CONSTRAINT fk_eval_run_sweep
        FOREIGN KEY (sweep_id) REFERENCES evaluation_sweep (id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_eval_run_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model (id) ON DELETE SET NULL,
    ADD INDEX idx_eval_run_sweep (sweep_id);

-- ai_run_id에는 의도적으로 FK를 걸지 않는다(Design D11).
-- ai_run은 관측 데이터라 보존정책상 선삭제될 수 있고, 관측 삭제가 평가 결과를
-- 지우면 안 된다. 조인 실패 시 비용·지연 지표만 N/A로 낙하시킨다.
ALTER TABLE evaluation_result
    ADD COLUMN ai_run_id VARCHAR(36) NULL
        COMMENT '이 케이스 실행의 ai_run.id — 토큰·비용·지연 회수 조인 키 (FK 없음)' AFTER run_id,
    ADD COLUMN tools_used JSON NULL
        COMMENT '실제 호출된 도구 이름 배열 — expected_tools와 집합 비교(F1 산출)',
    ADD INDEX idx_eval_result_ai_run (ai_run_id);
