-- Migration: V003__create_agent_definition.sql
-- Created: 2026-04-02
-- Description: Create agent_definition table
--
-- Table: agent_definition
-- Source: idt/src/infrastructure/agent_builder/models.py

CREATE TABLE agent_definition (
	id VARCHAR(36) NOT NULL,
	user_id VARCHAR(100) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	system_prompt TEXT NOT NULL,
	flow_hint TEXT,
	model_name VARCHAR(100) NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	INDEX ix_agent_definition_user_id (user_id)
);
