-- V027__create_user_permissions.sql
-- agent-user-context Design §5.2:
--   user 추가 권한 grant. role_permissions 와 합집합으로 최종 권한 산출.

CREATE TABLE user_permissions (
    user_id         BIGINT      NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    granted_at      DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by      BIGINT      NULL,
    PRIMARY KEY (user_id, permission_code),
    CONSTRAINT fk_user_perm_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_perm_code FOREIGN KEY (permission_code)
        REFERENCES permissions(code) ON DELETE CASCADE,
    CONSTRAINT fk_user_perm_granter FOREIGN KEY (granted_by)
        REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
