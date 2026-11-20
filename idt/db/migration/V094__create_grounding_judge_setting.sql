-- answer-citation-verification Design §3.3 (V094): 근거 판정 모델 전역 설정 — 단일 행(id 고정).
-- llm 모델 id 는 llm_model.id 소프트 참조(FK 없음 — V065 multimodal_setting·V086 선례).
-- NULL 이면 env GROUNDING_JUDGE_MODEL 을 쓴다(Design D-16).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE grounding_judge_setting (
    id                 VARCHAR(36) NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    judge_llm_model_id VARCHAR(36) NULL COMMENT 'llm_model.id 소프트 참조 — NULL이면 env 설정 사용',
    updated_by         VARCHAR(36) NULL COMMENT '마지막으로 바꾼 관리자 user_id',
    created_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='근거 판정 모델 전역 설정 — 단일 행';

INSERT INTO grounding_judge_setting (id) VALUES ('c0000000-0000-4000-8000-000000000094');
