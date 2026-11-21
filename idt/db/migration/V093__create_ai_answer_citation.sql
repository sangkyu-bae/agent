-- answer-citation-verification Design §3.3 (V093): 답변 인용 검증 결과 — 실행당 1행.
-- run_id 는 ai_run.id 소프트 참조(FK 없음 — 실행 삭제 후 고아 행은 조회 키가 run_id 라 무해).
-- 행이 없으면 인용 미적용(not_applicable), 행이 있고 인용 0건이면 none (Design D-12).
-- CHARSET/COLLATE 명시 금지 (errno 3780 회피). ⚠️ COMMENT 안에 콤마 금지.

CREATE TABLE ai_answer_citation (
    run_id      VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT 'ai_run.id 소프트 참조 — 실행당 1행',
    status      VARCHAR(16)  NOT NULL COMMENT '검증 결과 verified 또는 none',
    none_reason VARCHAR(32)  NULL COMMENT 'none 사유 no_markers 또는 all_rejected 또는 judge_failed',
    citations   JSON         NOT NULL COMMENT '검증된 인용 목록 — no와 chunk_id와 page와 evidence와 sentence',
    judge_model VARCHAR(100) NULL COMMENT '판정에 쓴 모델 이름 — 감사용',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각'
) ENGINE=InnoDB COMMENT='답변 인용 검증 결과 — 실행당 1행';
