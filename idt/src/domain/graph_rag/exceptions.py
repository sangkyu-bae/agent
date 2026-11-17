"""graph_rag 도메인 예외 — 라우터가 Design §6.1 오류 코드로 매핑한다."""


class GraphRagError(Exception):
    code = "GRAPH_RAG_ERROR"


class GraphStageEvalRequiredError(GraphRagError):
    """general 전환에 평가 근거도 강제 사유도 없다 (409)."""

    code = "GRAPH_STAGE_EVAL_REQUIRED"


class GraphStageOffError(GraphRagError):
    """stage=off 에서 추출·검색·검토 API 호출 (409)."""

    code = "GRAPH_STAGE_OFF"


class GraphBackendUnavailableError(GraphRagError):
    """Neo4j 미설정·연결 실패·Aura 정지 (503)."""

    code = "GRAPH_BACKEND_UNAVAILABLE"


class GraphEmbeddingDimMismatchError(GraphRagError):
    """기존 벡터 인덱스 차원 ≠ 설정 차원 — 모듈을 켜지 않는다 (기동 로그)."""

    code = "GRAPH_EMBEDDING_DIM_MISMATCH"
