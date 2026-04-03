from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "mysql+asyncmy://user:password@localhost:3306/idt"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "documents"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_llm_model: str = "gpt-4o-mini"

    # Anthropic
    anthropic_api_key: str = ""

    # LlamaParse
    llama_parse_api_key: str = ""

    # Parser
    parser_type: str = "pymupdf"

    # Chunking
    default_chunk_size: int = 1000
    default_chunk_overlap: int = 100

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

    # Application
    debug: bool = False


settings = Settings()
