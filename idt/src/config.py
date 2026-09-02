from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "mysql+asyncmy://user:password@localhost:3306/idt"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "documents"

    # LLM Wiki (LLM-WIKI-001)
    wiki_collection_name: str = "wiki_knowledge"
    # wiki-agentic-navigation D8: 프롬프트 목차 상한 (초과 시 최신순 절단)
    wiki_toc_max_items: int = 50
    wiki_toc_max_bytes: int = 4000
    # wiki-folder-summaries D5: 폴더 요약 계층 (기본 off — V053 배포 선행 필요)
    wiki_folder_summaries_enabled: bool = False
    wiki_folder_mode_threshold: int = 30

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_llm_model: str = "gpt-4o-mini"

    # Utility LLM Routing (admin-default-llm-routing Design §10.3)
    # 보조 LLM(의도 판정·환각 검사·요약 등)이 사용할 모델명.
    # 미설정(None)이면 관리자가 지정한 기본 모델(is_default=True)을 따라간다
    # — NPU 등 self-host 전면 테스트 시 비워둘 것.
    utility_llm_model_name: str | None = None
    # L1 값 캐시 TTL(초). 다중 워커 전환 시 무효화 미전파 구간의 안전장치.
    llm_model_cache_ttl_seconds: float = 60.0
    # L2 인스턴스 캐시 상한. (model_id, updated_at, temperature) 키 기준.
    llm_instance_cache_max_entries: int = 32

    # Agent Composer (nl-agent-composer)
    # compose LLM에 주입하는 후보 도구 상한. 초과분은 절단 + 경고 로그.
    composer_max_candidates: int = 100

    # Anthropic
    anthropic_api_key: str = ""

    # LlamaParse
    llama_parse_api_key: str = ""

    # Parser
    parser_type: str = "pymupdf"
    # KB 엑셀 업로드 시트당 행 수 상한 — 초과 시 422 (kb-excel-upload D6)
    kb_excel_max_rows_per_sheet: int = 20000

    # Chunking
    default_chunk_size: int = 1000
    default_chunk_overlap: int = 100

    # RAG Retrieval
    # 벡터 코사인 유사도 컷오프 전역 기본값 (0.0 = 비활성).
    # 에이전트별 RagToolConfig.score_threshold가 None일 때 사용된다.
    rag_vector_score_threshold: float = 0.0

    # Elasticsearch
    es_host: str = "localhost"
    es_port: int = 9200
    es_scheme: str = "http"
    es_index: str = "documents"
    es_username: str = ""
    es_password: str = ""
    es_ca_certs: str = ""
    es_max_retries: int = 3
    es_retry_on_timeout: bool = True
    es_request_timeout: int = 30

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_max_connections: int = 20

    # LangSmith
    langsmith_tracing: bool = False
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str = ""

    # Tavily
    tavily_api_key: str = ""

    # Agent Runtime (runtime-datetime-context D11)
    # 런타임 시스템 프롬프트 `[현재 날짜]` 블록의 기준 타임존 (IANA 이름).
    # 소비 지점: src/api/main.py 가 아래 생성자에 agent_timezone= 으로 주입 →
    #   WorkflowCompiler / GeneralChatUseCase / RAGAgentUseCase / ExcelAnalysisWorkflow
    #   → src/application/agent_run/prompt_rendering.py:render_datetime_block(tz)
    # application 레이어는 이 설정을 직접 import하지 않는다 (kwarg 주입만).
    agent_timezone: str = "Asia/Seoul"

    # Analysis
    analysis_max_retries: int = 3
    analysis_retry_on_hallucination: bool = True
    analysis_require_web_search_on_retry: bool = True
    analysis_min_confidence_score: float = 0.7
    analysis_max_hallucination_score: float = 0.3

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3.2"
    ollama_max_tokens: int = 4096
    ollama_temperature: float = 0.7
    ollama_timeout: int = 120

    # Chart Builder
    # chart-builder: 한 응답에 포함할 최대 차트 개수 (Design D1).
    chart_max_count: int = 3

    # Analysis Snapshot (analysis-data-continuity Design §3.8)
    # 분석 원천 데이터 스냅샷 — 항목/총량 상한(문자), 재주입할 최신 스냅샷 수.
    # 상한 근거: compact 후 총량(요약 ≤512자 + 최근 3메시지 + 스냅샷) 기준.
    analysis_snapshot_item_max_chars: int = 4000
    analysis_snapshot_total_max_chars: int = 8000
    analysis_snapshot_retention: int = 2
    # General Chat 스냅샷 수집 제외 도구 (콤마 구분) — 웹 스니펫은 데이터성 낮음.
    analysis_snapshot_excluded_tools: str = "tavily_search"

    # Analysis Source Preservation (analysis-source-preservation Design §3.5)
    # 엑셀 원천 데이터(raw_source)는 비-raw 항목과 독립 budget으로 상한한다.
    analysis_snapshot_raw_source_max_chars: int = 6000        # raw 항목당 상한(직렬화 후)
    analysis_snapshot_raw_source_total_max_chars: int = 8000  # raw 전용 total budget
    analysis_snapshot_raw_source_max_rows: int = 200          # 행 샘플링 임계

    # Search Pipeline (search-node-query-pipeline)
    # search 노드 rewrite/validate/compress용 경량 LLM. 빈 값이면 per-run 에이전트 LLM 사용.
    search_pipeline_provider: str = "openai"
    search_pipeline_model_name: str = "gpt-4o-mini"

    # deep-search-pipeline FR-13/AD-2: search 노드 파이프라인 선택.
    # "legacy"=rewrite→search→validate→compress (기본, 무영향)
    # "deep"=요구 분해→병렬 검색→근거 누적→커버리지 검증→선택적 재검색 (웹검색 한정)
    # 알 수 없는 값은 경고와 함께 legacy로 폴백한다.
    search_pipeline_mode: str = "legacy"
    # 검색결과 압축 발동 임계 길이(자). 이하면 원문 그대로 전달.
    search_compress_threshold: int = 4000

    # Tool Selector (tool-recommender Design §10.3)
    # 바인딩 직전 유저 질의 기준으로 도구를 좁히는 경량 LLM 셀렉터.
    tool_selector_provider: str = "openai"
    tool_selector_model_name: str = "gpt-4o-mini"
    tool_selector_top_k: int = 8            # 선별 상한. 후보가 이하면 LLM 미호출
    tool_selector_timeout_sec: float = 3.0  # 초과 시 필수 세트로 폴백
    tool_selector_enabled: bool = False     # 킬스위치. 결선(module-4)에서 활성화

    # Agent Attachment (ws-agent-excel-attachment Design §10.2)
    # 빈 값이면 main.py에서 {tempdir}/agent_attachments 로 해석한다.
    agent_attachment_upload_dir: str = ""
    agent_attachment_max_bytes: int = 10 * 1024 * 1024  # 10 MiB
    agent_attachment_ttl_seconds: int = 3600  # TTL 백업 정리 기준

    # Document Extractor (document-template-extractor Design §5)
    document_extractor_max_file_mb: int = 20          # 업로드 상한 (R8)
    document_extractor_max_slots: int = 30            # 슬롯 개수 상한
    document_extractor_max_regen: int = 10            # refine/재생성 상한 (R5)
    # 슬롯 추출 LLM 입력 HTML 상한(문자) — 모델 TPM 한도 초과(429) 방지
    document_extractor_llm_html_max_chars: int = 20000
    # 원본 영구 보관 디렉토리 (D3). 빈 값이면 main.py에서 uploads/document_templates 해석.
    document_template_dir: str = ""
    # 기본 MCP 변환 도구 id ("mcp_{uuid}") — extract 요청에 미지정 시 폴백 (D5).
    document_extractor_pdf_to_html_tool_id: str = ""
    document_extractor_html_to_doc_tool_id: str = ""
    # 미리보기 전용 layout 변환 (doc-extractor-preview-highlight D9).
    # "layout"=PDF 미리보기 이원화 활성, "off"=비활성(text HTML 폴백).
    document_extractor_preview_mode: str = "layout"
    document_extractor_preview_dpi: int = 120         # 72~300 (MCP 계약)

    # Document Generator (doc-generator Design §4-5)
    document_generator_max_sections: int = 20         # 섹션 개수 상한
    # 작성 LLM 입력(근거/대화 각각) 상한(문자) — 모델 TPM 한도 초과(429) 방지
    document_generator_llm_input_max_chars: int = 20000
    # 기본 MCP 변환 도구 id — 빈 값이면 extractor 키로 폴백 (D5 체인)
    document_generator_html_to_doc_tool_id: str = ""

    # golden-sample-blueprint (Design §8.3) — 선택 env. 비전 모델·동시성은 multimodal_setting
    blueprint_font_dir: str = ""                      # 서버 설치 폰트 디렉토리(빈 값 = 기본 폰트만)
    blueprint_default_font: str = "NanumGothic"       # 미매핑 폰트 대체 기본 폰트명

    # MCP Registry
    # transport별 인증/서버 config(auth_config/server_config)를 DB 저장 시
    # Fernet 대칭암호화하는 키 (urlsafe base64 32B). 빈 값이면 암호화 비활성(SSE 호환).
    # 키 생성: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    mcp_secret_key: str = ""

    # mcp-tool-auto-sync R-03: MCP 서버 등록/수정 직후 수행하는 도구 카탈로그
    # 동기화의 대기 상한(초). 초과하면 sync만 중단하고 등록/수정은 성공시킨다(FR-03).
    # 선례: tool_selector_timeout_sec
    mcp_tool_sync_timeout_sec: float = 10.0

    # Agent Schedule (agent-schedule)
    # 외부 트리거(POST /internal/schedules/trigger) 인증 토큰.
    # 빈 값이면 트리거 비활성(503). 외부 cron 이 X-Scheduler-Token 헤더로 전달.
    scheduler_trigger_token: str = ""

    # Section Summary (card-section-summary Design D17)
    # 섹션 요약 백그라운드 잡 — LLM 동시 호출 상한 / LLM 입력 절단(문자) /
    # stale 판정 기준(초, 서버 재시작 고아 복구) / 문서당 섹션 수 상한(초과 시 잡 failed).
    section_summary_concurrency: int = 3
    section_summary_input_char_cap: int = 12000
    section_summary_stale_seconds: int = 600
    section_summary_max_sections: int = 500

    # Document Summary (document-summary-routing Design D14)
    # 문서 요약 LLM 입력 상한(문자, 단일 패스/배치 분할 기준) / 계층 요약 배치 수 상한.
    document_summary_input_char_cap: int = 24000
    document_summary_max_batches: int = 10

    # Eval Hub — 문서→QA 초안 생성 (eval-hub Design A6)
    # LLM 입력 절단 상한(문자, 429 방지) / 1회 생성 QA 쌍 상한 / 생성 모델 / 업로드 파일 크기 상한(MB)
    eval_qa_gen_max_input_chars: int = 20000
    eval_qa_gen_max_pairs: int = 15
    eval_qa_gen_model: str = "gpt-4o-mini"
    eval_qa_gen_max_file_mb: int = 15

    # PII Masking (pii-masking)
    # 외부 LLM 경계의 가역 PII 마스킹 전역 on/off. false면 mask/unmask는 no-op.
    pii_masking_enabled: bool = True
    # 활성 PII 타입(쉼표 구분): rrn,phone,email,card,account
    pii_masking_types: str = "rrn,phone,email,card,account"
    # 응답에서 vault에 없는 신규 PII를 [REDACTED_<TYPE>]로 처리할지 여부.
    pii_masking_output_redact: bool = True

    # Agent Memory (agent-memory Design §3-4)
    # 사용자당 활성 메모리 개수 상한 / 주입 블록 문자 예산(한글 1자≈1토큰 보수 근사)
    memory_max_active_per_user: int = 30
    memory_inject_token_cap: int = 800
    # agent-memory-org-scope: 부서(org) 공유 메모리 개수 상한
    memory_max_active_per_department: int = 50

    # Agent Memory Extraction (agent-memory-extraction Design §3-4)
    # 대화 후 백그라운드 후보 추출 — 기본 off 배포, 검증 후 on.
    memory_extraction_enabled: bool = False
    memory_extraction_model_name: str = "gpt-4o-mini"
    memory_extraction_max_per_turn: int = 3
    memory_max_pending_per_user: int = 20

    # Agent Eval Gate (agent-eval-gate)
    # 관리자 최근 부정 피드백 조회 상한
    eval_recent_negative_limit: int = 20

    # Recurring Feedback Promotion (recurring-feedback-promotion §3-1)
    # 같은 주제 반복 👎 → 기존 draft 강화(refs 지지·confidence 가중) — 독립 opt-in.
    wiki_feedback_reinforce_enabled: bool = False

    # Eval Feedback Loop (eval-feedback-loop §3-1)
    # 이유(comment) 있는 👎 저장 시 부정 맥락 메모리 추출 트리거.
    # memory_extraction_enabled(매 턴 추출)와 독립 opt-in — 기본 off 배포.
    eval_feedback_extraction_enabled: bool = False

    # Wiki Feedback Loop (wiki-feedback-loop §3-1)
    # 이유 있는 👎 → 위키 draft 환류 — memory 환류와 독립 opt-in, 기본 off.
    wiki_feedback_draft_enabled: bool = False

    # Background Jobs (background-jobs Design §4-4)
    # 워커 루프 기동 스위치 (D13) — 테스트/도구 실행 시 false 로 무회귀 보장.
    background_worker_enabled: bool = True
    background_job_poll_interval_sec: float = 5.0
    background_job_max_concurrency: int = 2
    # 내장 스케줄러 틱 주기 (D1) — 외부 cron 대체
    background_schedule_tick_interval_sec: float = 30.0

    # Application
    debug: bool = False


settings = Settings()
