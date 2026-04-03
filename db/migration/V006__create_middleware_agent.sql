-- Migration: V006__create_middleware_agent.sql
-- Created: 2026-04-02
-- Description: Create middleware_agent table
--
-- Table: middleware_agent
-- Source: idt/src/infrastructure/middleware_agent/models.py

CREATE TABLE middleware_agent (
	id VARCHAR(36) NOT NULL,
	user_id VARCHAR(100) NOT NULL,
	name VARCHAR(200) NOT NULL,
	description TEXT,
	system_prompt TEXT NOT NULL,
	model_name VARCHAR(100) NOT NULL,
	status VARCHAR(20) NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	INDEX ix_middleware_agent_user_id (user_id)
);
