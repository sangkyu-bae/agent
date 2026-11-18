-- graph-rag-foundation Design §11.9 (module-4b 주제 분류, 2026-11-17 사용자 승인 DDL).
-- 2단계 주제 목록(대분류 > 소분류). 관리자 기본 목록 + 자동 추가(status=pending).
-- parent_id 는 소프트 참조(FK 없음). parent_key 는 유일성 검사용(대분류는 빈 값).
-- CHARSET/COLLATE 명시 금지. COMMENT 안 콤마 금지.

CREATE TABLE graph_topic (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '주제 식별자',
    name              VARCHAR(64)  NOT NULL COMMENT '주제 이름',
    normalized_name   VARCHAR(64)  NOT NULL COMMENT '정규화 이름 — 중복 검사용',
    level             TINYINT      NOT NULL COMMENT '1 대분류 또는 2 소분류',
    parent_id         VARCHAR(36)  NULL COMMENT '소분류의 대분류 id 소프트 참조',
    parent_key        VARCHAR(36)  NOT NULL DEFAULT '' COMMENT '유일성 검사용 — 대분류는 빈 값',
    description       VARCHAR(500) NULL COMMENT '판정과 질문 라우팅에 쓰는 설명',
    status            VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active 또는 pending 또는 retired',
    origin            VARCHAR(16)  NOT NULL COMMENT 'admin 또는 auto',
    created_by        VARCHAR(36)  NULL COMMENT '만든 관리자 id — 자동 생성은 NULL',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    UNIQUE KEY uq_graph_topic_name (parent_key, normalized_name),
    INDEX idx_graph_topic_level (level, status)
) ENGINE=InnoDB COMMENT='그래프 검색 범위용 문서 주제 목록 — 2단계';
