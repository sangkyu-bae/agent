-- multimodal-extractor Design §3.3 (V065): 멀티모달 추출 전역 설정 — 단일 행(id 고정).
-- vision_model_id 는 llm_model.id 소프트 참조(FK 없음 — chunking_profile.summary_llm_model_id 선례).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). 열거값은 VARCHAR(애플리케이션 검증 — ENUM 은 additive 확장 방해).
-- 범위 검증은 도메인 VO MultimodalSettings.__post_init__ 가 단일 출처.
-- ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE multimodal_setting (
    id                 VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    enabled            TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '멀티모달 추출 활성 여부',
    vision_model_id    VARCHAR(36)  NULL COMMENT 'llm_model.id 소프트 참조 — NULL이면 미설정',
    max_images_per_doc INT          NOT NULL DEFAULT 50 COMMENT '문서당 비전 호출 상한 — 초과분은 skipped',
    min_image_px       INT          NOT NULL DEFAULT 100 COMMENT '가로·세로 최소 픽셀 — 미만은 필터 제외',
    min_area_ratio     DECIMAL(5,4) NOT NULL DEFAULT 0.0200 COMMENT '페이지 면적 대비 최소 비율 — 미만은 필터 제외',
    concurrency        INT          NOT NULL DEFAULT 4 COMMENT '동시 비전 호출 수',
    timeout_sec        INT          NOT NULL DEFAULT 60 COMMENT '건당 비전 호출 타임아웃(초)',
    output_language    VARCHAR(8)   NOT NULL DEFAULT 'ko' COMMENT '설명 출력 언어 ko 또는 en',
    detail_level       VARCHAR(16)  NOT NULL DEFAULT 'detailed' COMMENT '설명 상세도 brief 또는 detailed',
    created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='멀티모달 추출 전역 설정 — 단일 행';

INSERT INTO multimodal_setting (id) VALUES ('b0000000-0000-4000-8000-000000000001');
