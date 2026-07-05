-- skill-builder Plan §5.1 / Design §3.3: 재사용 Skill(지시문+스크립트) 저장 테이블.
-- agent_definition의 소유/visibility/fork 구조(V007) 차용. 비밀값 없음(평문 TEXT).
-- 'trigger'는 MySQL 예약어 → 컬럼명 trigger_text. script_content는 저장 전용(실행 안 함).
CREATE TABLE skill_definition (
    id             VARCHAR(36)  PRIMARY KEY,
    user_id        VARCHAR(100) NOT NULL,
    name           VARCHAR(255) NOT NULL,
    description    TEXT         NOT NULL,
    trigger_text   TEXT         NULL COMMENT '사용 시점 설명(후속 에이전트 매칭 대비)',
    instruction    TEXT         NOT NULL COMMENT '지시문 본문(SKILL.md 본문)',
    script_type    VARCHAR(20)  NOT NULL DEFAULT 'none' COMMENT 'none|python|shell',
    script_content TEXT         NULL COMMENT '실행 스크립트 원문(저장 전용, 실행 안 함)',
    status         VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active|deleted (soft-delete)',
    visibility     ENUM('private','department','public') NOT NULL DEFAULT 'private',
    department_id  VARCHAR(36)  NULL,
    forked_from    VARCHAR(36)  NULL COMMENT 'Fork 원본 skill id',
    forked_at      DATETIME     NULL,
    created_at     DATETIME     NOT NULL,
    updated_at     DATETIME     NOT NULL,
    CONSTRAINT fk_skill_dept FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL,
    INDEX ix_skill_user        (user_id),
    INDEX ix_skill_visibility  (visibility),
    INDEX ix_skill_dept_vis    (department_id, visibility),
    INDEX ix_skill_status      (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
