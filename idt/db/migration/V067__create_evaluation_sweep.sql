-- agent-model-benchmark Design §3.3: 모델 스윕 = evaluation_run N건의 부모.
-- 재현성 스냅샷(judge/temperature/모델목록/테스트셋)을 여기 한 곳에 박제한다(D3).
-- 참조: docs/02-design/features/agent-model-benchmark.design.md

CREATE TABLE evaluation_sweep (
    id                  VARCHAR(36)    NOT NULL COMMENT '스윕 ID (UUID)',
    name                VARCHAR(200)   NOT NULL COMMENT '스윕 표시 이름',
    agent_id            VARCHAR(36)    NOT NULL COMMENT '피평가 에이전트 ID — 스윕 내내 고정',
    testset_id          VARCHAR(36)    NOT NULL COMMENT '평가에 사용한 테스트셋 ID (evaluation_testset.id)',
    judge_llm_model_id  VARCHAR(36)    NULL     COMMENT 'RAGAS 채점 judge 모델 ID — 실행 시점 박제',
    model_ids           JSON           NOT NULL COMMENT '피평가 모델 ID 배열 스냅샷 (최대 5개)',
    metrics             JSON           NOT NULL COMMENT '선택된 RAGAS 메트릭 이름 배열 스냅샷',
    temperature         DECIMAL(3,2)   NOT NULL DEFAULT 0.00 COMMENT '실행 temperature — 재현성 위해 항상 0',
    status              VARCHAR(20)    NOT NULL DEFAULT 'pending' COMMENT '진행 상태: pending/running/completed/failed',
    total_runs          INT            NOT NULL DEFAULT 0 COMMENT '생성된 하위 run 총 개수 (= 모델 수)',
    completed_runs      INT            NOT NULL DEFAULT 0 COMMENT '완료된 하위 run 개수 (진행률 산출용)',
    estimated_cost_usd  DECIMAL(12,6)  NULL     COMMENT '실행 전 추정 비용(USD) — 실제 비용과 대조용',
    user_id             VARCHAR(255)   NULL     COMMENT '스윕 소유자 — 미소유자에게는 404로 은닉',
    error_message       TEXT           NULL     COMMENT '스윕 수준 실패 사유 (개별 run 실패는 evaluation_run에 기록)',
    created_at          DATETIME       NOT NULL COMMENT '생성 시각',
    completed_at        DATETIME       NULL     COMMENT '전체 완료 시각',
    PRIMARY KEY (id),
    CONSTRAINT fk_sweep_judge_model
        FOREIGN KEY (judge_llm_model_id) REFERENCES llm_model (id) ON DELETE SET NULL,
    INDEX idx_sweep_user_created (user_id, created_at DESC),
    INDEX idx_sweep_agent (agent_id),
    INDEX idx_sweep_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='모델 스윕 — 동일 에이전트를 여러 LLM 모델로 순차 평가한 실험 1건';
