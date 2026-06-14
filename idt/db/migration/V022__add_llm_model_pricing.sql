-- AGENT-OBS-001 §5-0: llm_model에 가격 컬럼 추가.
-- 호출 시점 가격을 ai_llm_call에 스냅샷 저장하여 과거 비용 보존.
-- V021(ai_run.llm_model_id FK)이 의존하므로 V022가 먼저 적용되어야 한다.

ALTER TABLE llm_model
    ADD COLUMN input_price_per_1k_usd  DECIMAL(10, 6) NULL COMMENT '입력 토큰 1000개당 USD',
    ADD COLUMN output_price_per_1k_usd DECIMAL(10, 6) NULL COMMENT '출력 토큰 1000개당 USD',
    ADD COLUMN pricing_updated_at      DATETIME       NULL COMMENT '가격 최종 갱신 시각';

-- 초기 가격 시드 (2026-05 기준, OpenAI 공식가). 다른 모델은 운영팀이 수동 등록.
UPDATE llm_model SET
    input_price_per_1k_usd  = 0.005000,
    output_price_per_1k_usd = 0.015000,
    pricing_updated_at      = NOW()
WHERE provider = 'openai' AND model_name = 'gpt-4o';

UPDATE llm_model SET
    input_price_per_1k_usd  = 0.000150,
    output_price_per_1k_usd = 0.000600,
    pricing_updated_at      = NOW()
WHERE provider = 'openai' AND model_name = 'gpt-4o-mini';

UPDATE llm_model SET
    input_price_per_1k_usd  = 0.003000,
    output_price_per_1k_usd = 0.015000,
    pricing_updated_at      = NOW()
WHERE provider = 'anthropic' AND model_name LIKE 'claude-3-5-sonnet%';
