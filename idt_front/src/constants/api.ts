export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

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

  // Agent
  AGENT_RUN: '/api/agent/run',
  AGENT_RUN_STATUS: (runId: string) => `/api/agent/run/${runId}`,
  AGENT_STREAM: (runId: string) => `/api/agent/run/${runId}/stream`,

  // RAG / Documents
  DOCUMENTS: '/api/rag/documents',
  DOCUMENT_UPLOAD: '/api/rag/documents/upload',
  DOCUMENT_DELETE: (docId: string) => `/api/rag/documents/${docId}`,
  RETRIEVE: '/api/rag/retrieve',
  DOCUMENT_CHUNKS: (docId: string) => `/api/rag/documents/${docId}/chunks`,

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

  // RAG Tools (Custom RAG Config)
  RAG_TOOL_COLLECTIONS: '/api/v1/rag-tools/collections',
  RAG_TOOL_METADATA_KEYS: '/api/v1/rag-tools/metadata-keys',

  // LLM Models
  LLM_MODELS: '/api/v1/llm-models',

  // Admin — User approval
  ADMIN_USERS_PENDING: '/api/v1/admin/users/pending',
  ADMIN_USER_APPROVE: (userId: number) => `/api/v1/admin/users/${userId}/approve`,
  ADMIN_USER_REJECT: (userId: number) => `/api/v1/admin/users/${userId}/reject`,

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
  COLLECTION_ACTIVITY_LOG: '/api/v1/collections/activity-log',
  COLLECTION_ACTIVITY_LOG_BY_NAME: (name: string) =>
    `/api/v1/collections/${name}/activity-log`,
} as const;
