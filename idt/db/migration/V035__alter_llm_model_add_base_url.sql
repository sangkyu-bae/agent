-- LLM-MODEL-REG-002: self-host LLM 엔드포인트(vLLM/OpenAI 호환) 모델별 저장 (비파괴)
-- 기존 행은 base_url NULL → provider 기본 엔드포인트 사용, 동작 불변
ALTER TABLE llm_model
    ADD COLUMN base_url VARCHAR(500) NULL COMMENT 'self-host 엔드포인트(vLLM 등). NULL이면 provider 기본값' AFTER pricing_updated_at;
