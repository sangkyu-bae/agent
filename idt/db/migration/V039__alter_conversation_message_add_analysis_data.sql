-- analysis-data-continuity: 분석 원천 데이터 스냅샷 (NULL=없음)
ALTER TABLE conversation_message
    ADD COLUMN analysis_data JSON NULL COMMENT '분석 원천 데이터 스냅샷 (analysis-data-continuity)';
