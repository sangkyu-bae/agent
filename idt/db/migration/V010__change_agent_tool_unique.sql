-- V010: agent_tool 유니크 제약을 (agent_id, tool_id) → (agent_id, worker_id)로 변경
-- 다중 RAG 도구 지원: 같은 tool_id를 다른 worker_id로 복수 추가 가능
ALTER TABLE agent_tool DROP INDEX uq_agent_tool;

ALTER TABLE agent_tool
ADD CONSTRAINT uq_agent_worker UNIQUE (agent_id, worker_id);
