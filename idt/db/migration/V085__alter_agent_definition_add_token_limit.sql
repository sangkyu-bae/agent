-- V085__alter_agent_definition_add_token_limit.sql
-- agent-token-limit Design D1: supervisor 토큰 예산을 에이전트별로 둔다
--   (기본 50000 / 허용 범위 8000~500000 — 범위는 도메인 TokenLimitPolicy가 검증).
--   단위는 워커 산출 글자 수 ÷ 4의 누적 추정치이며 실제 LLM 토큰이 아니다.
--   기존 행은 DEFAULT 50000 적용. additive — 기존 CRUD·프론트 타입은 무변경으로 동작.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

ALTER TABLE agent_definition
  ADD COLUMN token_limit INT NOT NULL DEFAULT 50000
  COMMENT 'supervisor 토큰 예산 상한 — 워커 산출 글자수÷4 누적 추정치 기준이며 범위는 도메인 정책이 검증'
  AFTER max_iterations;
