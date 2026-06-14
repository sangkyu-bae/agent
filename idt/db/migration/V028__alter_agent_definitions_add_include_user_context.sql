-- V028__alter_agent_definitions_add_include_user_context.sql
-- agent-user-context Design §6.2:
--   향후 system bot 등 사용자 컨텍스트 prepend가 불필요한 agent를 opt-out하기 위한 슬롯.
--   현재 PR은 전역 자동 prepend (DEFAULT TRUE).

ALTER TABLE agent_definition
    ADD COLUMN include_user_context TINYINT(1) NOT NULL DEFAULT 1;
