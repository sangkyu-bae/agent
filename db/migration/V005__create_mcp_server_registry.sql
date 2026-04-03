-- Migration: V005__create_mcp_server_registry.sql
-- Created: 2026-04-02
-- Description: Create mcp_server_registry table
--
-- Table: mcp_server_registry
-- Source: idt/src/infrastructure/mcp_registry/models.py

CREATE TABLE mcp_server_registry (
	id VARCHAR(36) NOT NULL,
	user_id VARCHAR(100) NOT NULL,
	name VARCHAR(255) NOT NULL,
	description TEXT NOT NULL,
	endpoint VARCHAR(512) NOT NULL,
	transport VARCHAR(20) NOT NULL,
	input_schema JSON,
	is_active BOOL NOT NULL,
	created_at DATETIME NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	INDEX ix_mcp_server_registry_user_id (user_id),
	INDEX ix_mcp_server_registry_is_active (is_active)
);
