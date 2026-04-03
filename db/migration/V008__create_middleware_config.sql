-- Migration: V008__create_middleware_config.sql
-- Created: 2026-04-02
-- Description: Create middleware_config table
--
-- Table: middleware_config
-- Source: idt/src/infrastructure/middleware_agent/models.py
-- Depends on: V006__create_middleware_agent.sql

CREATE TABLE middleware_config (
	id INTEGER NOT NULL AUTO_INCREMENT,
	agent_id VARCHAR(36) NOT NULL,
	middleware_type VARCHAR(100) NOT NULL,
	config_json JSON,
	sort_order INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY (agent_id) REFERENCES middleware_agent (id) ON DELETE CASCADE
);
