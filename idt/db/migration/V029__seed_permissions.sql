-- V029__seed_permissions.sql
-- agent-user-context Design §5.2:
--   초기 권한 코드 8개 + role 매핑.
--   PermissionCode enum과 1:1 매칭 — 변경 시 src/domain/permission/value_objects.py 동기화.

INSERT INTO permissions (code, description) VALUES
    ('READ_PUBLIC_DOCS',        '사내 공개 문서 조회'),
    ('READ_INTERNAL_NOTICES',   '내부 공지 조회'),
    ('READ_DEPARTMENT_DOCS',    '소속 부서 문서 조회'),
    ('USE_RAG_SEARCH',          'RAG 검색 도구 사용'),
    ('USE_WEB_SEARCH',          '웹 검색 도구 사용'),
    ('CREATE_AGENT',            '에이전트 생성'),
    ('MANAGE_USERS',            '사용자 관리 (관리자)'),
    ('MANAGE_PERMISSIONS',      '권한 관리 (관리자)');

-- role 기본 권한:
--   user  : 일반 조회/검색/에이전트 생성
--   admin : user 권한 + 관리자 기능
INSERT INTO role_permissions (role, permission_code) VALUES
    ('user',  'READ_PUBLIC_DOCS'),
    ('user',  'READ_INTERNAL_NOTICES'),
    ('user',  'READ_DEPARTMENT_DOCS'),
    ('user',  'USE_RAG_SEARCH'),
    ('user',  'USE_WEB_SEARCH'),
    ('user',  'CREATE_AGENT'),
    ('admin', 'READ_PUBLIC_DOCS'),
    ('admin', 'READ_INTERNAL_NOTICES'),
    ('admin', 'READ_DEPARTMENT_DOCS'),
    ('admin', 'USE_RAG_SEARCH'),
    ('admin', 'USE_WEB_SEARCH'),
    ('admin', 'CREATE_AGENT'),
    ('admin', 'MANAGE_USERS'),
    ('admin', 'MANAGE_PERMISSIONS');
