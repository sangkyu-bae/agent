-- Migration: V002__create_conversation_summary.sql
-- Created: 2026-04-02
-- Description: Create conversation_summary table
--
-- Table: conversation_summary
-- Source: idt/src/infrastructure/persistence/models/conversation.py

CREATE TABLE conversation_summary (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id VARCHAR(255) NOT NULL,
	session_id VARCHAR(255) NOT NULL,
	summary_content TEXT NOT NULL,
	start_turn INTEGER NOT NULL,
	end_turn INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	INDEX ix_summary_user_session (user_id, session_id)
);
