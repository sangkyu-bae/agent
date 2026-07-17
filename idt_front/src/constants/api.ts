export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

// WebSocket base URL — VITE_WS_URL (e.g. ws://localhost:8000)
export const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';

// WebSocket endpoint paths (combine with wsUrl() in @/utils/wsUrl).
// Mirror to backend src/api/routes/ws_router.py.
export const WS_ENDPOINTS = {
  WS_ECHO: '/ws/echo',
  WS_AGENT_RUN: (runId: string) => `/ws/agent/${runId}`,
  WS_CHAT: (sessionId: string) => `/ws/chat/${sessionId}`,
} as const;

export const API_ENDPOINTS = {
  // General Chat (CHAT-001: POST /api/v1/chat)
  GENERAL_CHAT: '/api/v1/chat',

  // Conversation (CONV-001: POST /api/v1/conversation/chat)
  CONVERSATION_CHAT: '/api/v1/conversation/chat',

  // Chat (legacy — session management is client-side only)
  CHAT_SESSIONS: '/api/chat/sessions',
  CHAT_MESSAGE: '/api/chat/message',
  CHAT_STREAM: '/api/chat/stream',

  // Conversation History (CHAT-HIST-001)
  CONVERSATION_SESSIONS: '/api/v1/conversations/sessions',
  CONVERSATION_SESSION_MESSAGES: (sessionId: string) =>
    `/api/v1/conversations/sessions/${sessionId}/messages`,

  // Conversation History — Agent-scoped
  CONVERSATION_AGENT_SESSIONS: (agentId: string) =>
    `/api/v1/conversations/agents/${agentId}/sessions`,
  CONVERSATION_AGENT_SESSION_MESSAGES: (agentId: string, sessionId: string) =>
    `/api/v1/conversations/agents/${agentId}/sessions/${sessionId}/messages`,

  // Agent
  AGENT_RUN: '/api/agent/run',
  AGENT_RUN_STATUS: (runId: string) => `/api/agent/run/${runId}`,
  AGENT_STREAM: (runId: string) => `/api/agent/run/${runId}/stream`,
  AGENT_CHAT_RUN: (agentId: string) => `/api/v1/agents/${agentId}/run`,

  // Agent Attachment (ws-agent-excel-attachment) — 엑셀 업로드 → file_id 발급
  AGENT_ATTACHMENT_UPLOAD: '/api/v1/agent/attachments',

  // RAG / Documents
  DOCUMENTS: '/api/rag/documents',
  DOCUMENT_UPLOAD: '/api/rag/documents/upload',
  DOCUMENT_DELETE: (docId: string) => `/api/rag/documents/${docId}`,
  RETRIEVE: '/api/rag/retrieve',
  DOCUMENT_CHUNKS: (docId: string) => `/api/rag/documents/${docId}/chunks`,

  // Unified Document Upload
  DOCUMENT_UPLOAD_ALL: '/api/v1/documents/upload-all',

  // Eval Dataset
  EVAL_DATASET_EXTRACT: '/api/eval/extract',

  // Tools
  TOOL_CATALOG: '/api/v1/tool-catalog',
  TOOLS: '/api/tools',
  TOOL_TOGGLE: (toolId: string) => `/api/tools/${toolId}/toggle`,

  // Admin Tools (도구 관리)
  ADMIN_TOOLS: '/api/admin/tools',
  ADMIN_TOOL_DETAIL: (toolId: string) => `/api/admin/tools/${toolId}`,

  // Auth
  AUTH_REGISTER: '/api/v1/auth/register',
  AUTH_LOGIN: '/api/v1/auth/login',
  AUTH_REFRESH: '/api/v1/auth/refresh',
  AUTH_LOGOUT: '/api/v1/auth/logout',
  AUTH_ME: '/api/v1/auth/me',

  // Agent Subscription (legacy — used by agentSubscriptionService)
  AGENT_MY: '/api/v1/agents/my',
  AGENT_SUBSCRIBE: (agentId: string) => `/api/v1/agents/${agentId}/subscribe`,
  AGENT_FORK: (agentId: string) => `/api/v1/agents/${agentId}/fork`,
  AGENT_FORK_STATS: (agentId: string) => `/api/v1/agents/${agentId}/forks`,

  // Agent Store
  AGENT_STORE_LIST: '/api/v1/agents',
  AGENT_STORE_DETAIL: (agentId: string) => `/api/v1/agents/${agentId}`,
  AGENT_STORE_SUBSCRIBE: (agentId: string) => `/api/v1/agents/${agentId}/subscribe`,
  AGENT_STORE_FORK: (agentId: string) => `/api/v1/agents/${agentId}/fork`,
  AGENT_STORE_MY: '/api/v1/agents/my',
  AGENT_STORE_FORK_STATS: (agentId: string) => `/api/v1/agents/${agentId}/forks`,

  // RAG Tools (Custom RAG Config)
  RAG_TOOL_COLLECTIONS: '/api/v1/rag-tools/collections',
  RAG_TOOL_METADATA_KEYS: '/api/v1/rag-tools/metadata-keys',

  // Knowledge Bases (kb-rag-filter / kb-management-ui)
  KNOWLEDGE_BASES: '/api/v1/knowledge-bases',
  KNOWLEDGE_BASE_DETAIL: (kbId: string) => `/api/v1/knowledge-bases/${kbId}`,
  KNOWLEDGE_BASE_DOCUMENTS: (kbId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents`,
  // kb-custom-chunking D7: 청킹 설정 전체 교체
  KNOWLEDGE_BASE_CHUNKING: (kbId: string) =>
    `/api/v1/knowledge-bases/${kbId}/chunking`,
  // KB 저장 내용 조회 (kb-content-browser)
  KNOWLEDGE_BASE_DOCUMENT_SUMMARY: (kbId: string, docId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents/${docId}/summary`,
  KNOWLEDGE_BASE_SECTION_SUMMARIES: (kbId: string, docId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents/${docId}/section-summaries`,
  KNOWLEDGE_BASE_DOCUMENT_CHUNKS: (kbId: string, docId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents/${docId}/chunks`,
  KNOWLEDGE_BASE_SECTION_SUMMARY_STATUS: (kbId: string, docId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents/${docId}/section-summary`,
  KNOWLEDGE_BASE_SECTION_SUMMARY_RETRY: (kbId: string, docId: string) =>
    `/api/v1/knowledge-bases/${kbId}/documents/${docId}/section-summary/retry`,

  // LLM Models
  LLM_MODELS: '/api/v1/llm-models',
  LLM_MODEL_DETAIL: (id: string) => `/api/v1/llm-models/${id}`,
  LLM_MODEL_PRICING: (id: string) => `/api/v1/llm-models/${id}/pricing`,

  // Admin — Chunking Profiles (chunking-profile-admin-ui)
  ADMIN_CHUNKING_PROFILES: '/api/v1/admin/chunking/profiles',
  ADMIN_CHUNKING_PROFILE_DETAIL: (id: string) =>
    `/api/v1/admin/chunking/profiles/${id}`,
  ADMIN_CHUNKING_PROFILE_DEFAULT: (id: string) =>
    `/api/v1/admin/chunking/profiles/${id}/default`,

  // Admin — User approval
  ADMIN_USERS_PENDING: '/api/v1/admin/users/pending',
  ADMIN_USER_APPROVE: (userId: number) => `/api/v1/admin/users/${userId}/approve`,
  ADMIN_USER_REJECT: (userId: number) => `/api/v1/admin/users/${userId}/reject`,

  // Admin — User management (admin-user-registration)
  ADMIN_USERS_LIST: '/api/v1/admin/users',   // GET (?status=&q=&limit=&offset=)
  ADMIN_USERS_CREATE: '/api/v1/admin/users', // POST

  // Admin — RAGAS Evaluation
  ADMIN_RAGAS_DASHBOARD: '/api/v1/admin/ragas/dashboard',
  ADMIN_RAGAS_RUNS: '/api/v1/admin/ragas/runs',
  ADMIN_RAGAS_RUN_DETAIL: (runId: string) => `/api/v1/admin/ragas/runs/${runId}`,
  ADMIN_RAGAS_TESTSETS: '/api/v1/admin/ragas/testsets',

  // Admin — Department
  ADMIN_DEPARTMENTS: '/api/v1/departments',
  ADMIN_DEPARTMENT_DETAIL: (deptId: string) => `/api/v1/departments/${deptId}`,
  ADMIN_USER_DEPT_ASSIGN: (userId: number) => `/api/v1/users/${userId}/departments`,
  ADMIN_USER_DEPT_REMOVE: (userId: number, deptId: string) =>
    `/api/v1/users/${userId}/departments/${deptId}`,

  // Admin — MCP Server Registry
  MCP_SERVERS: '/api/v1/mcp-registry',
  MCP_SERVER_DETAIL: (id: string) => `/api/v1/mcp-registry/${id}`,
  MCP_SERVER_TEST: (id: string) => `/api/v1/mcp-registry/${id}/test`,

  // Admin — Skill Builder
  SKILLS: '/api/v1/skills',
  SKILLS_LIST: '/api/v1/skills/list',
  SKILLS_MY: '/api/v1/skills/my',
  SKILL_DETAIL: (id: string) => `/api/v1/skills/${id}`,
  SKILL_FORK: (id: string) => `/api/v1/skills/${id}/fork`,

  // Admin — Agent Run Observability (M5 dashboard)
  ADMIN_AGENT_RUN_DETAIL: (runId: string) => `/api/v1/agents/runs/${runId}`,
  ADMIN_AGENT_RUNS: '/api/v1/admin/runs',
  ADMIN_USAGE_BY_USER: '/api/v1/admin/usage/users',
  ADMIN_USAGE_BY_LLM: '/api/v1/admin/usage/llm-models',
  ADMIN_USAGE_BY_NODE: '/api/v1/admin/usage/by-node',
  ADMIN_USAGE_SUMMARY: '/api/v1/admin/usage/summary',
  ADMIN_USAGE_TIMESERIES: '/api/v1/admin/usage/timeseries',

  // User — My Usage
  USAGE_ME: '/api/v1/usage/me',
  USAGE_ME_RUNS: '/api/v1/usage/me/runs',
  USAGE_ME_TIMESERIES: '/api/v1/usage/me/timeseries',

  // Agent Builder (CRUD)
  AGENT_BUILDER_CREATE: '/api/v1/agents',
  AGENT_BUILDER_DETAIL: (agentId: string) => `/api/v1/agents/${agentId}`,
  AGENT_BUILDER_UPDATE: (agentId: string) => `/api/v1/agents/${agentId}`,
  AGENT_BUILDER_DELETE: (agentId: string) => `/api/v1/agents/${agentId}`,
  AGENT_AVAILABLE_SUB_AGENTS: '/api/v1/agents/available-sub-agents',
  // fix-agent-composer: 자연어 → 에이전트 초안 조합 (무저장)
  AGENT_COMPOSE: '/api/v1/agents/compose',

  // Document Extractor (document-template-extractor)
  DOCUMENT_EXTRACTOR_EXTRACT: '/api/v1/document-extractor/extract',
  DOCUMENT_EXTRACTOR_REFINE: '/api/v1/document-extractor/refine',
  DOCUMENT_EXTRACTOR_FILE: (fileId: string) =>
    `/api/v1/document-extractor/files/${fileId}`,

  // Agent-Skill Attach (skill-agent-integration Phase A)
  AGENT_SKILLS: (agentId: string) => `/api/v1/agents/${agentId}/skills`,
  AGENT_SKILL_DETACH: (agentId: string, skillId: string) =>
    `/api/v1/agents/${agentId}/skills/${skillId}`,

  // Agent Schedule (agent-schedule)
  AGENT_SCHEDULES: (agentId: string) => `/api/v1/agents/${agentId}/schedules`,
  AGENT_SCHEDULE_DETAIL: (agentId: string, scheduleId: string) =>
    `/api/v1/agents/${agentId}/schedules/${scheduleId}`,
  AGENT_SCHEDULE_ENABLED: (agentId: string, scheduleId: string) =>
    `/api/v1/agents/${agentId}/schedules/${scheduleId}/enabled`,
  AGENT_SCHEDULE_RUNS: (agentId: string, scheduleId: string) =>
    `/api/v1/agents/${agentId}/schedules/${scheduleId}/runs`,

  // Embedding Models
  EMBEDDING_MODELS: '/api/v1/embedding-models',

  // Collections (COLLECTION-MGMT)
  COLLECTIONS: '/api/v1/collections',
  COLLECTION_DETAIL: (name: string) => `/api/v1/collections/${name}`,
  COLLECTION_RENAME: (name: string) => `/api/v1/collections/${name}`,
  COLLECTION_DELETE: (name: string) => `/api/v1/collections/${name}`,
  COLLECTION_PERMISSION: (name: string) => `/api/v1/collections/${name}/permission`,
  COLLECTION_DOCUMENTS: (name: string) =>
    `/api/v1/collections/${name}/documents`,
  COLLECTION_DOCUMENT_CHUNKS: (name: string, documentId: string) =>
    `/api/v1/collections/${name}/documents/${documentId}/chunks`,
  COLLECTION_SEARCH: (name: string) =>
    `/api/v1/collections/${name}/search`,
  COLLECTION_SEARCH_HISTORY: (name: string) =>
    `/api/v1/collections/${name}/search-history`,
  COLLECTION_DOCUMENT_DELETE: (name: string, documentId: string) =>
    `/api/v1/collections/${name}/documents/${documentId}`,
  COLLECTION_DOCUMENTS_BATCH_DELETE: (name: string) =>
    `/api/v1/collections/${name}/documents`,
  COLLECTION_ACTIVITY_LOG: '/api/v1/collections/activity-log',
  COLLECTION_ACTIVITY_LOG_BY_NAME: (name: string) =>
    `/api/v1/collections/${name}/activity-log`,

  // ── Wiki (LLM-WIKI-001) ─────────────────────────────────
  WIKI_DISTILL: '/api/v1/wiki/distill',
  WIKI_LIST: '/api/v1/wiki',
  WIKI_DETAIL: (id: string) => `/api/v1/wiki/${id}`,
  WIKI_APPROVE: (id: string) => `/api/v1/wiki/${id}/approve`,
  WIKI_REJECT: (id: string) => `/api/v1/wiki/${id}/reject`,
  WIKI_DEPRECATE: (id: string) => `/api/v1/wiki/${id}/deprecate`,
  WIKI_RESTORE: (id: string) => `/api/v1/wiki/${id}/restore`,
  WIKI_UPDATE: (id: string) => `/api/v1/wiki/${id}`,
} as const;
