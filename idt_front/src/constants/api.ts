export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const API_ENDPOINTS = {
  // Conversation (CONV-001: POST /api/v1/conversation/chat)
  CONVERSATION_CHAT: '/api/v1/conversation/chat',

  // Chat (legacy — session management is client-side only)
  CHAT_SESSIONS: '/api/chat/sessions',
  CHAT_MESSAGE: '/api/chat/message',
  CHAT_STREAM: '/api/chat/stream',

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

  // Admin — User approval
  ADMIN_USERS_PENDING: '/api/v1/admin/users/pending',
  ADMIN_USER_APPROVE: (userId: number) => `/api/v1/admin/users/${userId}/approve`,
  ADMIN_USER_REJECT: (userId: number) => `/api/v1/admin/users/${userId}/reject`,
} as const;
