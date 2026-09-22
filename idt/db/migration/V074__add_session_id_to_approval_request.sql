-- approval-gate Check G1 수정.
-- 재개 답변을 저장할 원래 대화 세션. 이 값이 없으면 재개가 SessionId("")
-- 예외로 실패해 최종 답변이 유실됐다(Plan SUCCESS "최종 답변까지 도달" 위반).
-- NULL 허용: V071 로 이미 적재된 행은 세션을 모른다 — 그 경우 재개는 하되
-- 답변 저장만 건너뛴다.

ALTER TABLE approval_request
    ADD COLUMN session_id VARCHAR(100) NULL
    COMMENT '재개 답변을 저장할 원래 대화 세션 ID. NULL 이면 재개 답변을 저장하지 않는다(구버전 행)';
