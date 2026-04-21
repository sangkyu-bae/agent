-- V007__alter_agent_definition_add_sharing.sql
ALTER TABLE agent_definition
    ADD COLUMN visibility ENUM('private','department','public') NOT NULL DEFAULT 'private'
        AFTER status,
    ADD COLUMN department_id VARCHAR(36) NULL
        AFTER visibility,
    ADD COLUMN temperature DECIMAL(3,2) NOT NULL DEFAULT 0.70
        AFTER department_id,
    ADD CONSTRAINT fk_agent_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    ADD INDEX ix_agent_visibility (visibility),
    ADD INDEX ix_agent_dept_vis (department_id, visibility);

-- 기존 에이전트는 이전 코드 기본값(temperature=0) 보존
UPDATE agent_definition SET temperature = 0.00 WHERE temperature = 0.70;
