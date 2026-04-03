-- Migration: V001__create_conversation_message.sql
-- Created: 2026-04-02
-- Description: Create conversation_message table
--
-- Table: conversation_message
-- Source: idt/src/infrastructure/persistence/models/conversation.py

CREATE TABLE conversation_message (
	id INTEGER NOT NULL AUTO_INCREMENT,
	user_id VARCHAR(255) NOT NULL,
	session_id VARCHAR(255) NOT NULL,
	`role` VARCHAR(20) NOT NULL,
	content TEXT NOT NULL,
	turn_index INTEGER NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	INDEX ix_message_user_session (user_id, session_id)
);
