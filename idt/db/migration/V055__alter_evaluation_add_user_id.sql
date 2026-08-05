-- eval-hub: 평가 테스트셋·실행에 소유자 도입 (Design §2.1)
-- user_id NULL = 소유권 도입 이전 레거시 행 → admin만 열람, 일반 사용자 쿼리에서 제외
-- FK 미부여: V052 message_feedback 선례 — 사용자 삭제 시에도 평가 이력 보존

ALTER TABLE evaluation_testset
    ADD COLUMN user_id VARCHAR(36) NULL COMMENT '소유자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)',
    ADD INDEX ix_evaluation_testset_user_id (user_id);

ALTER TABLE evaluation_run
    ADD COLUMN user_id VARCHAR(36) NULL COMMENT '실행자 사용자 ID (NULL=소유권 도입 이전 레거시, admin만 열람)',
    ADD INDEX ix_evaluation_run_user_id (user_id);
