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

  // LLM Models
  LLM_MODELS: '/api/v1/llm-models',

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
} as const;
