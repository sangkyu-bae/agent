-- V009: agent_tool 테이블에 tool_config JSON 컬럼 추가 (RAG 도구 커스텀 설정)
ALTER TABLE agent_tool
ADD COLUMN tool_config JSON DEFAULT NULL
COMMENT 'Tool-specific configuration (e.g. RAG search scope, parameters)';
