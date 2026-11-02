-- image-generation-tool Design §3.3 (V081): 이미지 생성 모델을 같은 레지스트리에 두되 종류로 구분한다.
-- 채팅·비전·서브에이전트 모델 후보는 model_kind='chat' 만 노출하고 서버가 검증한다.
-- additive(기본 'chat')라 기존 CRUD·시드·프론트 타입은 무변경으로 동작한다.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

ALTER TABLE llm_model
  ADD COLUMN model_kind VARCHAR(16) NOT NULL DEFAULT 'chat'
  COMMENT '모델 종류 — chat(대화·비전) 또는 image(이미지 생성). 채팅 드롭다운은 chat 만 노출'
  AFTER supports_vision,
  ADD COLUMN price_per_image_usd DECIMAL(10,4) NULL
  COMMENT '이미지 생성 1장당 USD 단가 — model_kind=image 일 때만 사용하며 비용 원장에 합산'
  AFTER output_price_per_1k_usd;
