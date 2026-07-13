-- clause-aware-chunking Design §4.1:
-- 청킹 프로파일 — 조·항 경계 규칙(JSON) + 문서 유형별 기본 토큰/overlap.
-- 전역 기본 = is_default=1 (유일성은 UseCase 단일 세션이 보장, Design D3).
-- soft delete(status): KB가 참조 중일 수 있어 레코드 보존 (Design D11 폴백).
-- FK 콜레이션 주의(errno 3780): CHARSET/COLLATE 명시 금지, DB 기본 상속 (V037 선례).
CREATE TABLE chunking_profile (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY,
    name              VARCHAR(100) NOT NULL,
    description       VARCHAR(500) NULL,
    boundary_rules    JSON         NOT NULL COMMENT '[{"pattern","priority","level":"parent|child"}]',
    parent_chunk_size INT          NOT NULL DEFAULT 2000 COMMENT '조(parent) 토큰 상한',
    chunk_size        INT          NOT NULL DEFAULT 500  COMMENT 'child 토큰 상한',
    chunk_overlap     INT          NOT NULL DEFAULT 50   COMMENT '토큰 분할 시 overlap',
    is_default        TINYINT(1)   NOT NULL DEFAULT 0,
    status            VARCHAR(20)  NOT NULL DEFAULT 'active' COMMENT 'active | deleted',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_chunking_profile_status (status),
    INDEX idx_chunking_profile_default (is_default, status)
) ENGINE=InnoDB;

-- 기본 프로파일 시드 (Design D4) — 기존 하드코딩 기본값(2000/500/50)과 동일.
-- 패턴은 backslash 없이 문자 클래스로 표기(MySQL 리터럴 이스케이프 회피).
--   parent: 제N조 / 제N조의N (조 경계)
--   child : 항(①…) / 호(N.) / 목(가.)  — 선행 공백 허용
INSERT INTO chunking_profile
    (id, name, description, boundary_rules, parent_chunk_size, chunk_size, chunk_overlap, is_default)
VALUES (
    'a0000000-0000-4000-8000-000000000001',
    '법령·규정 기본',
    '제N조/제N조의N을 조(parent) 경계로, 항(①…) 및 호(N.)/목(가.)를 child 경계로 분할',
    JSON_ARRAY(
        JSON_OBJECT('pattern', '^제[0-9]+조의[0-9]+', 'priority', 1, 'level', 'parent'),
        JSON_OBJECT('pattern', '^제[0-9]+조',         'priority', 2, 'level', 'parent'),
        JSON_OBJECT('pattern', '^[ ]*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]',            'priority', 1, 'level', 'child'),
        JSON_OBJECT('pattern', '^[ ]*[0-9]+[.]',                          'priority', 2, 'level', 'child'),
        JSON_OBJECT('pattern', '^[ ]*[가나다라마바사아자차카타파하][.]',    'priority', 3, 'level', 'child')
    ),
    2000, 500, 50, 1
);
