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

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_llm_model: str = "gpt-4o-mini"

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
    # 검색결과 압축 발동 임계 길이(자). 이하면 원문 그대로 전달.
    search_compress_threshold: int = 4000

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

    # MCP Registry
    # transport별 인증/서버 config(auth_config/server_config)를 DB 저장 시
    # Fernet 대칭암호화하는 키 (urlsafe base64 32B). 빈 값이면 암호화 비활성(SSE 호환).
    # 키 생성: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    mcp_secret_key: str = ""

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

    # Agent Memory Extraction (agent-memory-extraction Design §3-4)
    # 대화 후 백그라운드 후보 추출 — 기본 off 배포, 검증 후 on.
    memory_extraction_enabled: bool = False
    memory_extraction_model_name: str = "gpt-4o-mini"
    memory_extraction_max_per_turn: int = 3
    memory_max_pending_per_user: int = 20

    # Application
    debug: bool = False


settings = Settings()
