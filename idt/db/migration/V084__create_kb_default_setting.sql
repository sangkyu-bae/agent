-- agent-kb-quick-setup Design §3.3 (V084): 지식베이스 자동 구성 전역 기본값 — 단일 행(id 고정).
-- default_embedding_model_id 는 embedding_model.id 소프트 참조(FK 없음 — multimodal_setting.vision_model_id 선례).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). ⚠️ COMMENT 안에 콤마 금지.
-- 미설정(NULL)이면 KB 자동 생성이 422 로 거부된다 (Plan FR-03) — 조용한 폴백 없음.

CREATE TABLE kb_default_setting (
    id                         VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    default_embedding_model_id INT         NULL COMMENT 'embedding_model.id 소프트 참조 — NULL이면 미설정',
    created_at                 DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at                 DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='지식베이스 자동 구성 전역 기본값 — 단일 행';

INSERT INTO kb_default_setting (id) VALUES ('c0000000-0000-4000-8000-000000000001');
