-- multimodal-extractor Design §3.3 (V064): 비전(이미지 입력) 지원 여부.
-- 비전 모델 선택 드롭다운은 is_active=1 AND supports_vision=1 만 노출한다.
-- additive(기본 0)라 기존 CRUD·시드·프론트 타입은 무변경으로 동작한다.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

ALTER TABLE llm_model
  ADD COLUMN supports_vision TINYINT(1) NOT NULL DEFAULT 0
  COMMENT '이미지 입력(비전) 지원 여부 — 1이면 멀티모달 추출 모델로 선택 가능'
  AFTER base_url;

-- 시드 기본 모델 백필 (seed.py DEFAULT_MODELS 와 동일 기준)
UPDATE llm_model SET supports_vision = 1
 WHERE (provider = 'openai'    AND model_name IN ('gpt-4o', 'gpt-4o-mini'))
    OR (provider = 'anthropic' AND model_name LIKE 'claude-%');
