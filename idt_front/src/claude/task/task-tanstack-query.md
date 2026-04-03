# TQ-001 — TanStack Query 공통 구성

## 상태: 완료

## 목표
채팅, 문서(RAG), Agent 도메인 전반에서 일관되게 사용할 수 있는
TanStack Query(React Query v5) 공통 인프라 구성.

## 완료된 작업

### 공통 인프라
- [x] `lib/queryClient.ts` — QueryClient 싱글톤 (공통 defaultOptions)
- [x] `lib/queryKeys.ts` — 쿼리 키 팩토리 (중앙 집중 관리)
- [x] `main.tsx` — QueryClientProvider 등록

### 도메인별 쿼리 훅
- [x] `hooks/useChat.ts` — 채팅 세션 목록 조회, 메시지 전송
- [x] `hooks/useDocuments.ts` — 문서 목록 조회, 업로드, 삭제
- [x] `hooks/useAgent.ts` — Agent 실행 시작, 실행 상태 폴링

---

## 공통 설정 상세

### QueryClient defaultOptions

| 옵션 | 값 | 설명 |
|------|------|------|
| `staleTime` | 60,000ms (1분) | 리패치 억제 기간 |
| `gcTime` | 300,000ms (5분) | 언마운트 후 캐시 보존 기간 |
| `retry` | 1 | 쿼리 실패 시 1회 재시도 |
| `refetchOnWindowFocus` | false | 창 포커스 시 자동 리패치 비활성 |
| `mutation.retry` | 0 | 뮤테이션 재시도 없음 |

---

## 쿼리 키 구조

```typescript
queryKeys.chat.all               // ['chat']
queryKeys.chat.sessions()        // ['chat', 'sessions']
queryKeys.chat.session(id)       // ['chat', 'sessions', id]

queryKeys.documents.all          // ['documents']
queryKeys.documents.list()       // ['documents', 'list']
queryKeys.documents.detail(id)   // ['documents', 'list', id]

queryKeys.agent.all              // ['agent']
queryKeys.agent.run(runId)       // ['agent', 'run', runId]
```

> **규칙**: 도메인 전체 무효화 시 `all` 키 사용, 특정 항목 무효화 시 세부 키 사용.

---

## 도메인별 훅 상세

### useChat.ts

| 훅 | 종류 | 설명 |
|----|------|------|
| `useChatSessions()` | useQuery | 채팅 세션 목록 조회 |
| `useSendMessage()` | useMutation | 메시지 전송 → 세션 캐시 무효화 |

### useDocuments.ts

| 훅 | 종류 | 설명 |
|----|------|------|
| `useDocuments()` | useQuery | 문서 목록 조회 |
| `useUploadDocument()` | useMutation | 파일 업로드 → 목록 무효화 |
| `useDeleteDocument()` | useMutation | 문서 삭제 → 목록 무효화 |

### useAgent.ts

| 훅 | 종류 | 설명 |
|----|------|------|
| `useAgentRunStatus(runId)` | useQuery | Agent 실행 상태 폴링 (2초 간격, `idle`복귀 또는 `error` 시 중단) |
| `useRunAgent()` | useMutation | Agent 실행 시작 |

---

## 사용 패턴

```typescript
// 목록 조회
const { data, isLoading, error } = useDocuments();

// 뮤테이션
const { mutate, isPending } = useUploadDocument();
mutate({ file, metadata });

// Agent 폴링 (runId 없으면 enabled:false로 대기)
const [runId, setRunId] = useState<string | null>(null);
const { data: runStatus } = useAgentRunStatus(runId);

const { mutate: runAgent } = useRunAgent();
runAgent({ input }, { onSuccess: (res) => setRunId(res.data.runId) });
```

---

## 캐시 무효화 규칙

```typescript
// 특정 목록 무효화
queryClient.invalidateQueries({ queryKey: queryKeys.documents.list() });

// 도메인 전체 무효화
queryClient.invalidateQueries({ queryKey: queryKeys.chat.all });

// 특정 항목 즉시 제거
queryClient.removeQueries({ queryKey: queryKeys.agent.run(runId) });
```

## 진행 예정 작업

- [ ] `ChatPage` Mock 데이터 제거 → `useChatSessions` 연결
- [ ] 문서 업로드 UI에 `useUploadDocument` 연결
- [ ] Agent 실행 플로우에 `useRunAgent` + `useAgentRunStatus` 연결
