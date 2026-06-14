-- V025__create_permissions.sql
-- agent-user-context Design §5.2:
--   permissions 마스터 테이블. code(PK)는 PermissionCode enum과 1:1.
--   변경 시 src/domain/permission/value_objects.py와 동기화 필요.

CREATE TABLE permissions (
    code        VARCHAR(64)  NOT NULL PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
