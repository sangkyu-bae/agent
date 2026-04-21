-- V006__create_tool_catalog.sql
CREATE TABLE tool_catalog (
    id            VARCHAR(36)  NOT NULL PRIMARY KEY,
    tool_id       VARCHAR(150) NOT NULL,
    source        ENUM('internal','mcp') NOT NULL,
    mcp_server_id VARCHAR(36)  NULL,
    name          VARCHAR(200) NOT NULL,
    description   TEXT         NOT NULL,
    requires_env  JSON         NULL,
    is_active     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL,
    updated_at    DATETIME     NOT NULL,
    UNIQUE KEY uq_tool_id (tool_id),
    CONSTRAINT fk_tc_mcp FOREIGN KEY (mcp_server_id) REFERENCES mcp_server_registry(id) ON DELETE CASCADE,
    INDEX ix_source_active (source, is_active),
    INDEX ix_mcp_server (mcp_server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
