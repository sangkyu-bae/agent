-- V008__seed_internal_tools.sql
INSERT INTO tool_catalog (id, tool_id, source, mcp_server_id, name, description, requires_env, is_active, created_at, updated_at) VALUES
(UUID(), 'internal:excel_export', 'internal', NULL,
 'Excel 파일 생성',
 'pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다. 수집된 데이터를 표 형태로 저장하거나 보고서가 필요할 때 사용하세요.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:internal_document_search', 'internal', NULL,
 '내부 문서 검색',
 '내부 벡터 DB(Qdrant)와 ES에서 BM25+Vector 하이브리드 검색으로 관련 문서를 찾습니다.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:python_code_executor', 'internal', NULL,
 'Python 코드 실행',
 '샌드박스 환경에서 Python 코드를 실행합니다. 계산, 데이터 처리, 알고리즘 실행이 필요할 때 사용하세요.',
 NULL, 1, NOW(), NOW()),
(UUID(), 'internal:tavily_search', 'internal', NULL,
 'Tavily 웹 검색',
 'Tavily API로 최신 웹 정보를 검색합니다. 실시간 뉴스, 최신 트렌드, 외부 정보가 필요할 때 사용하세요.',
 '["TAVILY_API_KEY"]', 1, NOW(), NOW());

-- 기존 agent_tool.tool_id에 'internal:' prefix 추가
UPDATE agent_tool
SET tool_id = CONCAT('internal:', tool_id)
WHERE tool_id NOT LIKE 'internal:%' AND tool_id NOT LIKE 'mcp_%';
