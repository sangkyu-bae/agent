-- conversation_message에 agent_id 추가
ALTER TABLE conversation_message
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

-- conversation_summary에 agent_id 추가
ALTER TABLE conversation_summary
  ADD COLUMN agent_id VARCHAR(36) NOT NULL DEFAULT 'super';

-- 에이전트별 조회 인덱스
CREATE INDEX ix_message_user_agent
  ON conversation_message (user_id, agent_id);

CREATE INDEX ix_summary_user_agent
  ON conversation_summary (user_id, agent_id);
