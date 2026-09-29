-- approval-edit-before-approve Design §3.4 — 담당자 수정 후 승인.
-- 집행은 tool_args 를 그대로 쓰므로 수정본은 tool_args/draft 에 확정되고,
-- 원본은 감사용으로 original_tool_args 에 보존한다. 세 컬럼 모두 NULL=무수정이라
-- 기존 행·기존 승인 경로는 영향이 없다.

ALTER TABLE approval_request
    ADD COLUMN original_tool_args JSON NULL
        COMMENT '담당자 수정 전 원본 도구 인자. NULL=무수정 (approval-edit-before-approve)' AFTER draft,
    ADD COLUMN edited_by VARCHAR(100) NULL
        COMMENT '초안을 수정해 승인한 사용자 ID. NULL=무수정' AFTER original_tool_args,
    ADD COLUMN edited_at DATETIME NULL
        COMMENT '초안 수정 확정 시각(UTC). NULL=무수정' AFTER edited_by;
