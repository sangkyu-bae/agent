-- chat-chart-persistence: assistant 메시지의 Chart.js config 배열 (N개, NULL=차트 없음)
ALTER TABLE conversation_message
    ADD COLUMN charts JSON NULL COMMENT 'Chart.js config 배열 (chat-chart-persistence)';
