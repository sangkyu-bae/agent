-- V045__alter_agent_definition_add_max_iterations.sql
-- agent-recursion-limit Design D4:
--   에이전트별 supervisor 반복 한도 (기본 25, 허용 범위 10~1000 — 범위는 도메인 정책 검증).
--   기존 행은 DEFAULT 25 적용. 실행 시 LangGraph recursion_limit은 이 값에서 파생.

ALTER TABLE agent_definition
    ADD COLUMN max_iterations INT NOT NULL DEFAULT 25;
