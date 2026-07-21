-- agent-eval-gate: 답변(assistant 메시지) 사용자 평가.
-- FK/COLLATE 명시 없음 (V037 주석 선례), ENGINE=InnoDB.
CREATE TABLE message_feedback (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    message_id  BIGINT       NOT NULL COMMENT 'conversation_message.id (assistant)',
    user_id     VARCHAR(255) NOT NULL,
    agent_id    VARCHAR(64)  NOT NULL COMMENT '메시지 agent_id 파생(general-chat 포함)',
    rating      VARCHAR(4)   NOT NULL COMMENT 'up|down',
    comment     VARCHAR(500) NULL,
    created_at  DATETIME     NOT NULL,
    updated_at  DATETIME     NOT NULL,
    UNIQUE KEY uq_feedback_msg_user (message_id, user_id),
    INDEX idx_feedback_agent_rating (agent_id, rating)
) ENGINE=InnoDB;
