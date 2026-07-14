"""애플리케이션 레이어 요청/응답 스키마."""
from pydantic import BaseModel, Field

from src.application.document_extractor.schemas import TemplateSlotDto


class DocumentTemplateRequest(BaseModel):
    """document-template-extractor Design §3-4: 확정 템플릿 저장 요청.

    프론트가 확정 시 sample_value를 {{key}}로 치환한 html_skeleton을 보낸다(D2).
    백엔드는 TemplateTokenPolicy로 검증만 수행. tool_configs와 분리된 전용 필드
    (기존 RAG 경로 무회귀).
    """

    name: str = Field(..., max_length=200)
    html_skeleton: str
    slots: list[TemplateSlotDto] = Field(..., min_length=1)
    source_file_id: str = Field(..., description="extract가 발급한 임시 file_id")
    source_format: str = Field(..., pattern="^(pdf|docx)$")
    mcp_pdf_to_html_tool_id: str
    mcp_html_to_doc_tool_id: str


class RagToolConfigRequest(BaseModel):
    """RAG 도구 설정 요청 스키마."""
    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = Field(default_factory=dict)
    top_k: int = Field(5, ge=1, le=20)
    search_mode: str = Field("hybrid", pattern="^(hybrid|vector_only|bm25_only)$")
    rrf_k: int = Field(60, ge=1)
    tool_name: str = Field("내부 문서 검색", max_length=100)
    tool_description: str = Field("", max_length=500)
    # LLM-WIKI-001 Step6: 승인 위키 우선 검색 사용 여부
    use_wiki_first: bool = False
    # rag-routed-integration D1: 라우팅 검색 opt-in (기존 search_mode와 독립)
    use_routed_search: bool = False
    # kb-rag-filter: 논리 지식베이스 필터 opt-in — 지정 시 저장 UseCase가
    # 존재 검증 + 물리 컬렉션 고정(D1) + scope clamp(D7)를 수행한다.
    kb_id: str | None = None


class WorkerInfo(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int
    tool_config: dict | None = None
    worker_type: str = "tool"
    ref_agent_id: str | None = None
    ref_agent_name: str | None = None
    # compose-tool-instructions FR-03: 도구별 사용 지침 (compose 초안 전달용)
    instruction: str = ""


class SubAgentConfigRequest(BaseModel):
    """서브 에이전트 설정 요청 스키마."""
    ref_agent_id: str = Field(..., description="서브 에이전트로 사용할 에이전트 ID")
    description: str = Field("", max_length=500, description="상위 에이전트에서의 역할 설명")


class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str = ""
    llm_model_id: str | None = None
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)
    # agent-recursion-limit D10: supervisor 반복 한도 (미전달 시 25)
    max_iterations: int = Field(25, ge=10, le=1000)
    tool_ids: list[str] | None = None
    tool_configs: dict[str, RagToolConfigRequest] | None = None
    sub_agent_configs: list[SubAgentConfigRequest] | None = None
    # agent-skill-toggle: 등록 시점 부착 스킬(목표 상태). None/[] = 부착 없음.
    skill_ids: list[str] | None = None
    # document-template-extractor GA4: 확정 템플릿 (document_extractor 도구 필요)
    document_template: DocumentTemplateRequest | None = None
    # agent-instruction-required: 지침 필수. None/빈 값이면 생성 시 에러(자동생성 제거).
    # 자동 구성은 Fix 에이전트(agent_composer)가 초안을 프리필하는 방식으로만 제공.
    system_prompt: str | None = Field(None, max_length=4000)


class CreateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    tool_ids: list[str]
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    visibility: str
    visibility_clamped: bool = False
    max_visibility: str | None = None
    department_id: str | None = None
    temperature: float
    max_iterations: int = 25
    created_at: str
    has_sub_agents: bool = False


class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=200)
    visibility: str | None = Field(None, pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    # agent-recursion-limit D10: None = 반복 한도 변경 안 함
    max_iterations: int | None = Field(None, ge=10, le=1000)
    # None = 서브에이전트 변경 안 함, [] = 모든 서브에이전트 제거
    sub_agent_configs: list[SubAgentConfigRequest] | None = None
    # agent-skill-toggle: None = 스킬 변경 안 함, [] = 전부 해제, [...] = 목표 상태
    skill_ids: list[str] | None = None
    # document-template-extractor: None = 템플릿 변경 안 함, 값 = 교체(기존 soft-delete)
    document_template: DocumentTemplateRequest | None = None
    # agent-builder-edit-mapping FR-5: None = 모델 변경 안 함
    llm_model_id: str | None = None


class UpdateAgentResponse(BaseModel):
    agent_id: str
    name: str
    system_prompt: str
    updated_at: str


class GetAgentResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    system_prompt: str
    tool_ids: list[str]
    # agent-skill-toggle: 부착된 스킬 id 목록(sort_order ASC) — edit 폼 프라임용
    skill_ids: list[str] = []
    workers: list[WorkerInfo]
    flow_hint: str
    llm_model_id: str
    status: str
    visibility: str
    department_id: str | None = None
    department_name: str | None = None
    temperature: float
    # agent-recursion-limit D10: edit 폼 프라임용
    max_iterations: int = 25
    owner_user_id: str
    can_edit: bool
    can_delete: bool
    created_at: str
    updated_at: str


class RunAgentRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str
    session_id: str | None = None
    # analysis-node-agent: 분석 노드 입력용 첨부(엑셀 파일 경로 등).
    # 예: [{"type": "excel", "file_path": "/tmp/x.xlsx", "user_id": "u1"}]
    attachments: list[dict] | None = None


class RunAgentResponse(BaseModel):
    agent_id: str
    query: str
    answer: str
    tools_used: list[str]
    request_id: str
    session_id: str
    run_id: str | None = None  # AGENT-OBS-001: ai_run.id (관측성)


class ToolMetaResponse(BaseModel):
    tool_id: str
    name: str
    description: str
    configurable: bool = False
    config_schema: dict | None = None


class AvailableToolsResponse(BaseModel):
    tools: list[ToolMetaResponse]


# ── Sub-Agent Candidate ───────────────────────────────────────


class SubAgentCandidate(BaseModel):
    agent_id: str
    name: str
    description: str
    source_type: str  # "owned" | "public" | "department"
    tool_ids: list[str]
    has_sub_agents: bool = False
    llm_model_id: str | None = None  # 프론트가 provider:model_name 배지로 변환
    visibility: str | None = None    # 배지/필터 표시용


class AvailableSubAgentsResponse(BaseModel):
    agents: list[SubAgentCandidate]


# ── List / Delete ─────────────────────────────────────────────────


class ListAgentsRequest(BaseModel):
    scope: str = Field("all", pattern="^(mine|department|public|all)$")
    search: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class AgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    visibility: str
    department_name: str | None = None
    owner_user_id: str
    owner_email: str | None = None
    temperature: float
    can_edit: bool
    can_delete: bool
    created_at: str


class ListAgentsResponse(BaseModel):
    agents: list[AgentSummary]
    total: int
    page: int
    size: int


# ── Subscription / Fork / My Agents ──────────────────────────────


class SubscribeResponse(BaseModel):
    subscription_id: str
    agent_id: str
    agent_name: str
    is_pinned: bool
    subscribed_at: str


class UpdateSubscriptionRequest(BaseModel):
    is_pinned: bool


class ForkAgentRequest(BaseModel):
    name: str | None = Field(None, max_length=200)


class ForkAgentResponse(BaseModel):
    agent_id: str
    name: str
    forked_from: str
    forked_at: str
    system_prompt: str
    workers: list[WorkerInfo]
    visibility: str
    temperature: float
    llm_model_id: str


class MyAgentSummary(BaseModel):
    agent_id: str
    name: str
    description: str
    source_type: str
    visibility: str
    temperature: float
    owner_user_id: str
    forked_from: str | None = None
    is_pinned: bool = False
    created_at: str


class ListMyAgentsRequest(BaseModel):
    filter: str = Field("all", pattern="^(all|owned|subscribed|forked)$")
    search: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class ListMyAgentsResponse(BaseModel):
    agents: list[MyAgentSummary]
    total: int
    page: int
    size: int


class ForkStatsResponse(BaseModel):
    agent_id: str
    fork_count: int
    subscriber_count: int
