-- V018: agent_tool 테이블에 worker_type, ref_agent_id 추가 (멀티 에이전트 조합)
ALTER TABLE agent_tool
  ADD COLUMN worker_type VARCHAR(20) NOT NULL DEFAULT 'tool'
    AFTER tool_config,
  ADD COLUMN ref_agent_id VARCHAR(36) NULL
    AFTER worker_type;

ALTER TABLE agent_tool
  ADD CONSTRAINT fk_agent_tool_ref_agent
    FOREIGN KEY (ref_agent_id) REFERENCES agent_definition(id)
    ON DELETE SET NULL;

CREATE INDEX idx_agent_tool_ref_agent ON agent_tool(ref_agent_id);
