-- Migration: V004__create_agent_tool.sql
-- Created: 2026-04-02
-- Description: Create agent_tool table
--
-- Table: agent_tool
-- Source: idt/src/infrastructure/agent_builder/models.py
-- Depends on: V003__create_agent_definition.sql

CREATE TABLE agent_tool (
	id VARCHAR(36) NOT NULL,
	agent_id VARCHAR(36) NOT NULL,
	tool_id VARCHAR(100) NOT NULL,
	worker_id VARCHAR(100) NOT NULL,
	description TEXT,
	sort_order INTEGER NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_agent_tool UNIQUE (agent_id, tool_id),
	FOREIGN KEY (agent_id) REFERENCES agent_definition (id) ON DELETE CASCADE
);
