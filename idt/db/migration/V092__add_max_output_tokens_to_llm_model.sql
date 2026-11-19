-- claude-agent-e2e-fixes Design §3.1 (V092): 응답 출력 한도(요청 max_tokens).
-- 기존 max_tokens 는 컨텍스트 크기라 출력 한도로 쓸 수 없다.
-- NULL 이면 provider 기본값 — Anthropic 은 서버 설정 기본값(16000)을 쓴다.
-- additive(NULL 허용)라 기존 CRUD·시드·프론트 타입은 무변경으로 동작한다.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

ALTER TABLE llm_model
  ADD COLUMN max_output_tokens INT NULL
  COMMENT '응답 최대 출력 토큰 수 — NULL이면 provider 기본값 사용 (Anthropic은 서버 설정 기본값)'
  AFTER max_tokens;
