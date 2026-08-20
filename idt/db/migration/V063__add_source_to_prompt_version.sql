-- agent-create-wizard: 프롬프트 버전의 작성 주체 구분
-- Design: docs/02-design/features/agent-create-wizard.design.md §3.4
--
-- 위저드 4단계에서 사용자가 생성된 시스템 프롬프트를 직접 편집하면 그 편집본을
-- 새 버전으로 쌓는다. LLM 생성본과 사람 편집본을 구분해야 나중에 "LLM안 vs
-- 사람안"을 비교할 수 있다.
--
-- ENUM 이 아니라 VARCHAR(10) 인 이유: ENUM 은 값을 추가할 때마다 ALTER 가
--   필요해 additive 확장을 막는다. 값 검증은 애플리케이션 레이어가 한다.
-- DEFAULT 'llm': 기존 행이 전부 LLM 생성본이므로 백필이 자동으로 끝난다.
--   기존 compose 경로(POST /compose)는 이 컬럼을 명시하지 않아도 무변경 동작한다.
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 의
--   `_split_top_level` 이 따옴표를 추적하지 않아 허위 위반을 낸다.

ALTER TABLE prompt_version
  ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'llm'
  COMMENT '프롬프트 작성 주체 — llm(생성) 또는 human(사용자 편집본)'
  AFTER schema_version;
