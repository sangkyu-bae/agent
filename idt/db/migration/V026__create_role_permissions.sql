-- V026__create_role_permissions.sql
-- agent-user-context Design §5.2:
--   role(user/admin) 기본 권한 매핑.

CREATE TABLE role_permissions (
    role            VARCHAR(20) NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (role, permission_code),
    CONSTRAINT fk_role_perm_code FOREIGN KEY (permission_code)
        REFERENCES permissions(code) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
