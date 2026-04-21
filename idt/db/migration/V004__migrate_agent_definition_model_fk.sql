-- LLM-MODEL-REG-001: agent_definition.model_name → llm_model_id FK 교체
-- 참조: docs/02-design/features/llm-model-registry.design.md §3-2
--
-- 실행 순서:
--   V003 (llm_model 테이블 생성) → 시드 데이터 등록 (seed.py) → V004 (본 파일)
--   seed.py가 기본 모델 3개를 llm_model에 INSERT한 후 본 마이그레이션이 실행된다.

-- Step 1: llm_model_id 컬럼 추가 (nullable — 기존 레코드용)
ALTER TABLE agent_definition
    ADD COLUMN llm_model_id VARCHAR(36) NULL AFTER model_name;

-- Step 2: FK 제약 조건 추가 (llm_model.id 참조)
ALTER TABLE agent_definition
    ADD CONSTRAINT fk_agent_llm_model
        FOREIGN KEY (llm_model_id) REFERENCES llm_model (id)
        ON DELETE RESTRICT ON UPDATE CASCADE;

-- Step 3: 기존 model_name 컬럼 제거
ALTER TABLE agent_definition
    DROP COLUMN model_name;
