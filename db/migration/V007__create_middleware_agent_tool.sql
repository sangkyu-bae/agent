-- Migration: V007__create_middleware_agent_tool.sql
-- Created: 2026-04-02
-- Description: Create middleware_agent_tool table
--
-- Table: middleware_agent_tool
-- Source: idt/src/infrastructure/middleware_agent/models.py
-- Depends on: V006__create_middleware_agent.sql

CREATE TABLE middleware_agent_tool (
	id INTEGER NOT NULL AUTO_INCREMENT,
	agent_id VARCHAR(36) NOT NULL,
	tool_id VARCHAR(100) NOT NULL,
	sort_order INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_mw_agent_tool UNIQUE (agent_id, tool_id),
	FOREIGN KEY (agent_id) REFERENCES middleware_agent (id) ON DELETE CASCADE
);
