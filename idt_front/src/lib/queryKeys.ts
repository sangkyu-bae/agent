/**
 * TanStack Query 키 팩토리
 *
 * 모든 queryKey는 이 파일에서 중앙 관리합니다.
 * 계층적 구조로 정의하여 특정 도메인 전체 무효화가 가능합니다.
 *
 * 사용 예시:
 *   useQuery({ queryKey: queryKeys.chat.sessions() })
 *   queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
 */

export const queryKeys = {
  // ── Chat ───────────────────────────────────────────────
  chat: {
    /** 채팅 도메인 전체 키 — invalidateQueries 용 */
    all: ['chat'] as const,
    /** 세션 목록 */
    sessions: () => [...queryKeys.chat.all, 'sessions'] as const,
    /** 특정 세션 상세 */
    session: (sessionId: string) =>
      [...queryKeys.chat.sessions(), sessionId] as const,
  },

  // ── Documents ──────────────────────────────────────────
  documents: {
    /** 문서 도메인 전체 키 */
    all: ['documents'] as const,
    /** 문서 목록 */
    list: () => [...queryKeys.documents.all, 'list'] as const,
    /** 특정 문서 상세 */
    detail: (docId: string) =>
      [...queryKeys.documents.list(), docId] as const,
    /** 특정 문서의 청킹 결과 */
    chunks: (docId: string) =>
      [...queryKeys.documents.all, 'chunks', docId] as const,
    /** 벡터 검색 결과 */
    vectorSearch: (query: string, topK: number) =>
      [...queryKeys.documents.all, 'vectorSearch', query, topK] as const,
  },

  // ── Agent ──────────────────────────────────────────────
  agent: {
    /** Agent 도메인 전체 키 */
    all: ['agent'] as const,
    /** 특정 Agent 실행 상태 */
    run: (runId: string) =>
      [...queryKeys.agent.all, 'run', runId] as const,
  },

  // ── Auth ───────────────────────────────────────────────
  auth: {
    /** 인증 도메인 전체 키 */
    all: ['auth'] as const,
    /** 현재 사용자 정보 */
    me: () => [...queryKeys.auth.all, 'me'] as const,
    /** 앱 초기 토큰 복원 */
    init: () => [...queryKeys.auth.all, 'init'] as const,
  },

  // ── Admin ──────────────────────────────────────────────
  admin: {
    /** 관리자 도메인 전체 키 */
    all: ['admin'] as const,
    /** 승인 대기 사용자 목록 */
    pendingUsers: () => [...queryKeys.admin.all, 'pendingUsers'] as const,
  },
} as const;
