-- AGENT-OBS-001 §5: Agent Run 관측성 5개 테이블.
-- Plan §5 / Design §8 SQL 1:1 반영. V022(가격 컬럼) 적용 이후 실행되어야 한다.

-- 1) ai_run — 사용자 질문 1회 = 1 row
CREATE TABLE ai_run (
    id                  VARCHAR(36) PRIMARY KEY,
    conversation_id     VARCHAR(255) NOT NULL,
    user_id             VARCHAR(255) NOT NULL,
    agent_id            VARCHAR(36)  NOT NULL,
    llm_model_id        VARCHAR(36)  NULL COMMENT 'Agent 주력 LLM',
    user_message_id     INT          NULL COMMENT 'FK -> conversation_message.id (INT, matches conversation_message.id type)',
    status              VARCHAR(20)  NOT NULL COMMENT 'RUNNING/SUCCESS/FAILED/CANCELLED',
    langgraph_thread_id VARCHAR(150) NOT NULL,
    langsmith_trace_id  VARCHAR(150) NULL,
    langsmith_run_url   VARCHAR(500) NULL,
    prompt_tokens       INT            NOT NULL DEFAULT 0,
    completion_tokens   INT            NOT NULL DEFAULT 0,
    total_tokens        INT            NOT NULL DEFAULT 0,
    total_cost_usd      DECIMAL(12, 6) NOT NULL DEFAULT 0,
    llm_call_count      INT            NOT NULL DEFAULT 0,
    started_at          DATETIME       NOT NULL,
    ended_at            DATETIME       NULL,
    latency_ms          INT            NULL,
    error_message       TEXT           NULL,
    error_stack         TEXT           NULL,
    CONSTRAINT fk_run_user_message
        FOREIGN KEY (user_message_id) REFERENCES conversation_message(id) ON DELETE SET NULL,
    CONSTRAINT fk_run_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model(id) ON DELETE SET NULL,
    INDEX idx_run_conversation   (conversation_id),
    INDEX idx_run_agent          (agent_id),
    INDEX idx_run_user_started   (user_id, started_at DESC),
    INDEX idx_run_llm_model      (llm_model_id),
    INDEX idx_run_status         (status),
    INDEX idx_run_started_at     (started_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) ai_run_step — LangGraph 노드 실행
CREATE TABLE ai_run_step (
    id             VARCHAR(36)  PRIMARY KEY,
    run_id         VARCHAR(36)  NOT NULL,
    step_index     INT          NOT NULL,
    node_name      VARCHAR(100) NOT NULL,
    node_type      VARCHAR(30)  NOT NULL COMMENT 'SUPERVISOR/WORKER/GATE/OTHER',
    llm_model_id   VARCHAR(36)  NULL,
    status         VARCHAR(20)  NOT NULL COMMENT 'STARTED/SUCCESS/FAILED',
    input_summary  TEXT         NULL,
    output_summary TEXT         NULL,
    started_at     DATETIME     NOT NULL,
    ended_at       DATETIME     NULL,
    latency_ms     INT          NULL,
    error_text     TEXT         NULL,
    CONSTRAINT fk_step_run       FOREIGN KEY (run_id)       REFERENCES ai_run(id)    ON DELETE CASCADE,
    CONSTRAINT fk_step_llm_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id) ON DELETE SET NULL,
    INDEX idx_step_run (run_id, step_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) ai_tool_call — 툴 호출
CREATE TABLE ai_tool_call (
    id                VARCHAR(36)    PRIMARY KEY,
    run_id            VARCHAR(36)    NOT NULL,
    step_id           VARCHAR(36)    NULL,
    tool_name         VARCHAR(100)   NOT NULL,
    llm_model_id      VARCHAR(36)    NULL COMMENT '툴 내부 LLM 호출 시',
    arguments_json    JSON           NULL,
    result_summary    TEXT           NULL COMMENT '결과 미리보기 (1KB 컷)',
    result_json       JSON           NULL,
    prompt_tokens     INT            NULL,
    completion_tokens INT            NULL,
    total_tokens      INT            NULL,
    total_cost_usd    DECIMAL(12, 6) NULL,
    latency_ms        INT            NULL,
    status            VARCHAR(20)    NOT NULL COMMENT 'STARTED/SUCCESS/FAILED',
    error_text        TEXT           NULL,
    created_at        DATETIME       NOT NULL,
    CONSTRAINT fk_tool_run       FOREIGN KEY (run_id)       REFERENCES ai_run(id)        ON DELETE CASCADE,
    CONSTRAINT fk_tool_step      FOREIGN KEY (step_id)      REFERENCES ai_run_step(id)   ON DELETE SET NULL,
    CONSTRAINT fk_tool_llm_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id)     ON DELETE SET NULL,
    INDEX idx_tool_run       (run_id),
    INDEX idx_tool_name      (tool_name),
    INDEX idx_tool_llm_model (llm_model_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4) ai_llm_call — LLM API 호출 1건 (사용자별·LLM별 집계의 기준)
CREATE TABLE ai_llm_call (
    id                       VARCHAR(36)    PRIMARY KEY,
    run_id                   VARCHAR(36)    NOT NULL,
    step_id                  VARCHAR(36)    NULL,
    tool_call_id             VARCHAR(36)    NULL,
    user_id                  VARCHAR(255)   NOT NULL COMMENT '비정규화 (집계 성능)',
    agent_id                 VARCHAR(36)    NOT NULL COMMENT '비정규화 (집계 성능)',
    llm_model_id             VARCHAR(36)    NULL COMMENT '매핑 실패 시 NULL',
    provider                 VARCHAR(50)    NOT NULL,
    model_name               VARCHAR(150)   NOT NULL COMMENT '호출 시점 스냅샷',
    purpose                  VARCHAR(50)    NULL COMMENT 'supervisor/worker/summarizer/rerank/query_rewrite/hallucination_check',
    prompt_tokens            INT            NOT NULL DEFAULT 0,
    completion_tokens        INT            NOT NULL DEFAULT 0,
    total_tokens             INT            NOT NULL DEFAULT 0,
    input_price_per_1k_usd   DECIMAL(10, 6) NULL COMMENT '호출 시점 가격 스냅샷',
    output_price_per_1k_usd  DECIMAL(10, 6) NULL,
    input_cost_usd           DECIMAL(12, 6) NOT NULL DEFAULT 0,
    output_cost_usd          DECIMAL(12, 6) NOT NULL DEFAULT 0,
    total_cost_usd           DECIMAL(12, 6) NOT NULL DEFAULT 0,
    latency_ms               INT            NULL,
    status                   VARCHAR(20)    NOT NULL COMMENT 'SUCCESS/FAILED',
    error_text               TEXT           NULL,
    created_at               DATETIME       NOT NULL,
    CONSTRAINT fk_llm_call_run   FOREIGN KEY (run_id)       REFERENCES ai_run(id)       ON DELETE CASCADE,
    CONSTRAINT fk_llm_call_step  FOREIGN KEY (step_id)      REFERENCES ai_run_step(id)  ON DELETE SET NULL,
    CONSTRAINT fk_llm_call_tool  FOREIGN KEY (tool_call_id) REFERENCES ai_tool_call(id) ON DELETE SET NULL,
    CONSTRAINT fk_llm_call_model FOREIGN KEY (llm_model_id) REFERENCES llm_model(id),
    INDEX idx_llm_call_user_created  (user_id, created_at DESC),
    INDEX idx_llm_call_model_created (llm_model_id, created_at DESC),
    INDEX idx_llm_call_user_model    (user_id, llm_model_id),
    INDEX idx_llm_call_agent         (agent_id),
    INDEX idx_llm_call_run           (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5) ai_retrieval_source — RAG 검색 근거
CREATE TABLE ai_retrieval_source (
    id              VARCHAR(36)    PRIMARY KEY,
    run_id          VARCHAR(36)    NOT NULL,
    tool_call_id    VARCHAR(36)    NULL,
    collection_name VARCHAR(100)   NOT NULL,
    document_id     VARCHAR(150)   NULL,
    chunk_id        VARCHAR(150)   NULL,
    score           DECIMAL(10, 6) NULL,
    rank_index      INT            NULL,
    content_preview TEXT           NULL COMMENT 'chunk 텍스트 500자 컷',
    metadata_json   JSON           NULL,
    created_at      DATETIME       NOT NULL,
    CONSTRAINT fk_retrieval_run  FOREIGN KEY (run_id)       REFERENCES ai_run(id)        ON DELETE CASCADE,
    CONSTRAINT fk_retrieval_tool FOREIGN KEY (tool_call_id) REFERENCES ai_tool_call(id)  ON DELETE SET NULL,
    INDEX idx_retrieval_run        (run_id),
    INDEX idx_retrieval_collection (collection_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
