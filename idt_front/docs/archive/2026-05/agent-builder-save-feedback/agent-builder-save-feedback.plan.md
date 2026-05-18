# Plan: agent-builder-save-feedback

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | 에이전트 빌더 저장 결과 팝업 피드백 |
| Created | 2026-05-09 |
| Status | Draft |

### Value Delivered

| 관점 | 설명 |
|------|------|
| Problem | 에이전트 등록/수정 시 서버 오류가 발생해도 사용자에게 아무 피드백이 없고, 성공 시에도 알림 없이 목록 뷰로만 전환됨 |
| Solution | 서버 오류 시 에러 메시지 팝업, 성공 시 완료 팝업 후 확인 버튼 클릭 시 에이전트 목록(메인) 페이지로 네비게이션 |
| Function UX Effect | 사용자가 등록 결과를 즉시 인지하고, 성공 시 자연스럽게 메인 흐름으로 복귀 |
| Core Value | 에이전트 빌더 사용성 및 신뢰성 향상 |

---

## 1. 현재 상태 분석 (As-Is)

### 1.1 문제가 발생하는 코드

**파일**: `src/pages/AgentBuilderPage/index.tsx` — `handleSave()` (117~157행)

#### 생성(Create) 흐름 (132~156행)
```tsx
createMutation.mutate(
  { user_request: ..., name: ..., ... },
  {
    onSuccess: (response) => {
      if (form.systemPrompt.trim()) {
        updateMutation.mutate({ agentId: response.agent_id, data: { system_prompt: form.systemPrompt } });
      }
      setView('list');  // ← 팝업 없이 바로 목록 뷰로 전환
    },
    // ← onError 콜백 없음 → 서버 오류 시 아무 피드백 없음
  },
);
```

#### 수정(Update) 흐름 (120~131행)
```tsx
updateMutation.mutate(
  { agentId: editingId, data: { ... } },
  { onSuccess: () => setView('list') },  // ← 동일 문제
);
```

### 1.2 발견된 버그 3건

| # | 버그 | 심각도 | 원인 |
|---|------|--------|------|
| B1 | 서버 오류 시 사용자에게 아무 피드백이 없음 | **High** | `onError` 콜백 미정의 |
| B2 | 성공 시 완료 알림 없이 목록 뷰로 전환 | **Medium** | `onSuccess`에서 `setView('list')`만 호출 |
| B3 | 성공 후 에이전트 목록 페이지(`/agent-builder`)의 list 뷰로만 이동하고, 메인 페이지로 네비게이트하지 않음 | **Medium** | `useNavigate` 미사용, 뷰 상태만 변경 |

### 1.3 기존 인프라 분석

| 컴포넌트 | 파일 | 재사용 가능 여부 |
|----------|------|-----------------|
| `ConfirmDialog` | `src/components/common/ConfirmDialog.tsx` | **재사용 가능** — 이미 삭제 확인에 사용 중. `variant="info"` 지원. 단, 현재는 confirm+cancel 2버튼 구조 |
| `ApiError` | `src/services/api/ApiError.ts` | **활용 가능** — `authClient` 인터셉터에서 서버 에러 메시지를 `ApiError.message`로 변환 중 |
| `useCreateBuilderAgent` | `src/hooks/useAgentBuilder.ts` | mutation의 `error` 상태 활용 가능 (`createMutation.error.message`) |

---

## 2. 요구사항 (To-Be)

### 2.1 사용자 시나리오

#### 시나리오 A: 등록 성공
1. 사용자가 에이전트 정보 입력 후 "저장" 클릭
2. 서버 응답 성공
3. **성공 팝업** 표시: "에이전트가 등록되었습니다"
4. "확인" 버튼 클릭 → 에이전트 빌더 목록 뷰(list)로 이동

#### 시나리오 B: 등록 실패
1. 사용자가 에이전트 정보 입력 후 "저장" 클릭
2. 서버 응답 오류 (400, 422, 500 등)
3. **에러 팝업** 표시: 서버 에러 메시지 (ApiError.message)
4. "확인" 클릭 → 팝업 닫힘, 폼 유지 (입력값 보존)

#### 시나리오 C: 수정 성공
1. 수정 모드에서 "저장" 클릭
2. 서버 응답 성공
3. **성공 팝업** 표시: "에이전트가 수정되었습니다"
4. "확인" 클릭 → 목록 뷰로 이동

#### 시나리오 D: 수정 실패
1. 수정 모드에서 "저장" 클릭
2. 서버 응답 오류
3. **에러 팝업** 표시: 서버 에러 메시지
4. "확인" 클릭 → 팝업 닫힘, 폼 유지

### 2.2 팝업 UI 요구사항

| 구분 | 성공 팝업 | 에러 팝업 |
|------|----------|----------|
| variant | `info` | `danger` |
| 타이틀 | "에이전트 등록 완료" / "에이전트 수정 완료" | "등록 실패" / "수정 실패" |
| 설명 | "에이전트가 성공적으로 등록되었습니다" | 서버 에러 메시지 |
| 버튼 | "확인" (1개) | "확인" (1개) |
| 확인 후 동작 | 목록 뷰(list)로 이동 | 팝업 닫기 (폼 유지) |

---

## 3. 구현 계획

### 3.1 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `src/pages/AgentBuilderPage/index.tsx` | `handleSave`에 성공/에러 팝업 상태 추가, ConfirmDialog 연동 |

### 3.2 상세 구현 방안

#### 3.2.1 팝업 상태 추가

```tsx
// 새로 추가할 상태
const [saveResult, setSaveResult] = useState<{
  type: 'success' | 'error';
  message: string;
} | null>(null);
```

#### 3.2.2 handleSave 수정

**Create 성공 시:**
```tsx
onSuccess: (response) => {
  // systemPrompt 후처리 유지
  if (form.systemPrompt.trim()) {
    updateMutation.mutate({ ... });
  }
  // 팝업 표시 (뷰 전환은 팝업 확인 후)
  setSaveResult({ type: 'success', message: '에이전트가 성공적으로 등록되었습니다' });
},
onError: (error) => {
  setSaveResult({ type: 'error', message: error.message });
},
```

**Update 성공/실패 시:**
```tsx
onSuccess: () => {
  setSaveResult({ type: 'success', message: '에이전트가 성공적으로 수정되었습니다' });
},
onError: (error) => {
  setSaveResult({ type: 'error', message: error.message });
},
```

#### 3.2.3 팝업 확인 핸들러

```tsx
const handleSaveResultClose = () => {
  if (saveResult?.type === 'success') {
    setView('list');  // 목록 뷰로 이동
  }
  setSaveResult(null);
};
```

#### 3.2.4 ConfirmDialog 추가 (기존 컴포넌트 재사용)

```tsx
<ConfirmDialog
  isOpen={!!saveResult}
  title={saveResult?.type === 'success'
    ? (view === 'edit' ? '에이전트 수정 완료' : '에이전트 등록 완료')
    : (view === 'edit' ? '수정 실패' : '등록 실패')}
  description={saveResult?.message ?? ''}
  confirmLabel="확인"
  cancelLabel=""   // 취소 버튼 숨기기 → ConfirmDialog에서 cancelLabel 빈 문자열 처리 필요 확인
  variant={saveResult?.type === 'success' ? 'info' : 'danger'}
  onClose={handleSaveResultClose}
  onConfirm={handleSaveResultClose}
/>
```

> **참고**: `ConfirmDialog`의 취소 버튼을 숨기려면 `onClose`와 `onConfirm`을 동일하게 설정하면 취소 버튼도 같은 동작을 수행하므로 UX상 문제 없음. 취소 버튼을 완전히 숨기고 싶다면 `ConfirmDialog`에 `hideCancelButton` prop 추가가 필요하나, 최소 변경 원칙에 따라 동일 핸들러 바인딩으로 처리.

### 3.3 변경하지 않는 것

| 항목 | 이유 |
|------|------|
| `useAgentBuilder.ts` 훅 | 변경 불필요 — mutation의 onSuccess/onError는 호출부에서 오버라이드 가능 |
| `agentBuilderService.ts` | 변경 불필요 — API 호출 로직은 정상 |
| `ConfirmDialog.tsx` | 변경 최소화 — 기존 구조로 충분히 대응 가능 |
| `authClient.ts` | 변경 불필요 — ApiError 변환 이미 구현됨 |

---

## 4. 영향 범위

| 범위 | 영향도 | 설명 |
|------|--------|------|
| `AgentBuilderPage` | **직접** | handleSave 로직 + ConfirmDialog 1개 추가 |
| 다른 페이지 | **없음** | 에이전트 빌더 페이지 내부 변경만 |
| API 계약 | **없음** | 백엔드 변경 불필요 |

---

## 5. 체크리스트

- [ ] 에이전트 등록 성공 시 성공 팝업 표시
- [ ] 성공 팝업 "확인" 클릭 시 목록 뷰로 이동
- [ ] 에이전트 등록 실패 시 서버 에러 메시지 팝업 표시
- [ ] 에러 팝업 "확인" 클릭 시 팝업만 닫히고 폼 입력값 보존
- [ ] 에이전트 수정 성공/실패 시 동일한 팝업 동작
- [ ] 기존 삭제 확인 다이얼로그 동작에 영향 없음
