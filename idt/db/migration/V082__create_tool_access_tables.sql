-- tool-access-control Design §3.3 (V082): 도구 허용 규칙 3테이블 — 기본 세트 / 부서 / 사용자.
-- 판정 = admin 전부 허용 | 그 외 기본 세트 ∪ 소속 부서 허용 ∪ 사용자 허용 (합집합).
-- 규칙이 없는 도구는 기본 차단이다. 시드는 V083.
-- 대상별 진짜 FK 로 도구(카탈로그)·부서·사용자 삭제 시 규칙이 CASCADE 로 정리된다 (Plan FR-17).
-- tool_catalog 에 컬럼을 추가하지 않는다 — ORM 매핑 컬럼 추가는 미적용 시 카탈로그 조회 자체를 깨뜨린다.
-- ⚠️ CHARSET/COLLATE 명시 금지 — FK 참조 테이블과 collation 불일치 시 errno 3780 (위키 mysql-fk-collation).
-- ⚠️ COMMENT 안에 콤마 금지 — tests/db/test_migration_ddl_comments.py 파서 제약.

CREATE TABLE tool_access_default (
    tool_id     VARCHAR(150) NOT NULL COMMENT '카탈로그 표기 tool_id (internal:{id} 또는 mcp:{srv}:{tool})',
    granted_by  BIGINT       NULL     COMMENT '부여한 관리자 users.id — 시드 행은 NULL',
    granted_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '부여 시각',
    PRIMARY KEY (tool_id),
    CONSTRAINT fk_tad_tool FOREIGN KEY (tool_id)
        REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tad_granter FOREIGN KEY (granted_by)
        REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='기본 허용 도구 세트 — 모든 사용자에게 항상 적용';

CREATE TABLE tool_access_department (
    tool_id       VARCHAR(150) NOT NULL COMMENT '카탈로그 표기 tool_id',
    department_id VARCHAR(36)  NOT NULL COMMENT '허용 대상 departments.id',
    granted_by    BIGINT       NULL     COMMENT '부여한 관리자 users.id',
    granted_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '부여 시각',
    PRIMARY KEY (tool_id, department_id),
    INDEX ix_tadept_dept (department_id),
    CONSTRAINT fk_tadept_tool FOREIGN KEY (tool_id)
        REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tadept_dept FOREIGN KEY (department_id)
        REFERENCES departments(id) ON DELETE CASCADE,
    CONSTRAINT fk_tadept_granter FOREIGN KEY (granted_by)
        REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='부서 단위 도구 허용 — 소속 부서 중 하나라도 허용이면 사용 가능';

CREATE TABLE tool_access_user (
    tool_id     VARCHAR(150) NOT NULL COMMENT '카탈로그 표기 tool_id',
    user_id     BIGINT       NOT NULL COMMENT '허용 대상 users.id',
    granted_by  BIGINT       NULL     COMMENT '부여한 관리자 users.id',
    granted_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '부여 시각',
    PRIMARY KEY (tool_id, user_id),
    INDEX ix_tau_user (user_id),
    CONSTRAINT fk_tau_tool FOREIGN KEY (tool_id)
        REFERENCES tool_catalog(tool_id) ON DELETE CASCADE,
    CONSTRAINT fk_tau_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_tau_granter FOREIGN KEY (granted_by)
        REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='사용자 단위 도구 허용 — 기본 세트와 부서 허용에 더해지는 개인 허용';
