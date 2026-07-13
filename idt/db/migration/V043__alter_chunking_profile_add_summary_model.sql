-- card-section-summary Design D2: 섹션 요약용 LLM 모델 소프트 참조 (NULL = 요약 비활성).
-- FK 제약 없음 — llm_model은 deactivate 운영이라 무결성은 UseCase 검증(422)으로 담보.
-- (FK 콜레이션 errno 3780 리스크 회피 겸용, V037 선례)
ALTER TABLE chunking_profile
    ADD COLUMN summary_llm_model_id VARCHAR(36) NULL
        COMMENT '섹션 요약 LLM(llm_model.id 소프트 참조), NULL=요약 비활성';
