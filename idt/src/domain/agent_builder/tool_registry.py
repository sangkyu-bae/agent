"""TOOL_REGISTRY: 시스템에 등록된 도구 메타데이터."""
from src.domain.agent_builder.schemas import ToolMeta

TOOL_REGISTRY: dict[str, ToolMeta] = {
    "excel_export": ToolMeta(
        tool_id="excel_export",
        name="Excel 파일 생성",
        description=(
            "pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다. "
            "수집된 데이터를 표 형태로 저장하거나 보고서가 필요할 때 사용하세요."
        ),
        requires_env=[],
    ),
    "data_analysis": ToolMeta(
        tool_id="data_analysis",
        name="데이터 분석",
        description=(
            "수집된 검색 결과나 첨부된 엑셀 데이터를 사용자의 질문 기준으로 분석하고 "
            "분석 결과만 반환합니다. 검색 결과가 있으면 그것을, 없으면 전체 대화 문맥을 "
            "분석 대상으로 삼습니다. 엑셀 첨부 시 자가교정 분석 워크플로우를 사용합니다."
        ),
        requires_env=[],
        category="analysis",
    ),
    "internal_document_search": ToolMeta(
        tool_id="internal_document_search",
        name="내부 문서 검색",
        description=(
            "내부 벡터 DB(Qdrant)와 ES에서 BM25+Vector 하이브리드 검색으로 "
            "관련 문서를 찾습니다. 내부 정책/지식 기반 질의에 사용하세요."
        ),
        requires_env=[],
        category="search",
    ),
    "python_code_executor": ToolMeta(
        tool_id="python_code_executor",
        name="Python 코드 실행",
        description=(
            "샌드박스 환경에서 Python 코드를 실행합니다. "
            "계산, 데이터 처리, 알고리즘 실행이 필요할 때 사용하세요. "
            "파일 I/O, 네트워크 접근은 불가합니다."
        ),
        requires_env=[],
    ),
    "document_extractor": ToolMeta(
        tool_id="document_extractor",
        name="문서추출기",
        description=(
            "등록된 문서 양식(템플릿)을 대화와 수집된 근거로 채워 "
            "PDF/Word 파일로 생성합니다. 정형 문서(심의서·보고서) 자동 작성에 사용하세요."
        ),
        requires_env=[],
    ),
    "tavily_search": ToolMeta(
        tool_id="tavily_search",
        name="Tavily 웹 검색",
        description=(
            "Tavily API로 최신 웹 정보를 검색합니다. "
            "실시간 뉴스, 최신 트렌드, 외부 정보가 필요할 때 사용하세요."
        ),
        requires_env=["TAVILY_API_KEY"],
        category="search",
    ),
}


def get_tool_meta(tool_id: str) -> ToolMeta:
    """tool_id로 ToolMeta 조회. 없으면 ValueError."""
    if tool_id not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool_id: {tool_id!r}")
    return TOOL_REGISTRY[tool_id]


def get_all_tools() -> list[ToolMeta]:
    """전체 도구 목록 반환 (tool_id 알파벳 순)."""
    return sorted(TOOL_REGISTRY.values(), key=lambda t: t.tool_id)
