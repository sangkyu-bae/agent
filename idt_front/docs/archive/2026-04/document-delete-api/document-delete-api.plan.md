# document-delete-api Planning Document

> **Summary**: 컬렉션 문서 삭제 API 연동 — 단건/일괄 삭제 + 확인 다이얼로그 + 체크박스 선택 UI
>
> **Project**: IDT Front (idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-04-30
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

컬렉션 상세 페이지(`/collections/{name}/documents`)에서 문서를 삭제할 때,
백엔드 DELETE API를 호출하여 Qdrant 청크 + ES 청크 + MySQL 메타데이터를 3중 동기 삭제한다.

### 1.2 Background

현재 `DocumentTable.tsx`에 삭제 버튼 UI는 존재하지만 `// TODO: delete handler` 상태이다.
백엔드 API 구현이 완료되었으므로 프론트엔드 연동을 진행한다.

### 1.3 Related Documents

- API 스펙: `docs/api/document-delete-api.md`
- 컬렉션 관리 Plan: `docs/01-plan/features/collection-management-ui.plan.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 단건 문서 삭제 API 연동 (`DELETE /{collection_name}/documents/{document_id}`)
- [ ] 일괄 문서 삭제 API 연동 (`DELETE /{collection_name}/documents`)
- [ ] 체크박스 선택 UI (전체 선택 / 개별 선택)
- [ ] 공통 확인 다이얼로그 컴포넌트 (`ConfirmDialog`) 신규 생성
- [ ] 기존 `DeleteCollectionDialog`를 `ConfirmDialog` 기반으로 리팩터링
- [ ] 문서 삭제 확인에 `ConfirmDialog` 재사용 (단건/일괄 공통)
- [ ] X-User-Id 헤더 자동 주입 (authStore에서 추출)
- [ ] 삭제 후 문서 목록 자동 갱신 (queryClient.invalidateQueries)
- [ ] 에러 핸들링 (403 권한 없음, 404 문서 없음, 500 서버 오류)
- [ ] 일괄 삭제 시 부분 실패 결과 표시

### 2.2 Out of Scope

- 삭제 권한 관리 UI (권한은 백엔드에서 검증)
- 문서 복원(undo) 기능
- Activity Log 조회 UI (별도 기능)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 행별 삭제 버튼 클릭 시 확인 다이얼로그 표시 후 단건 삭제 API 호출 | High | Pending |
| FR-02 | 체크박스로 문서 선택 (개별 + 전체 선택/해제) | High | Pending |
| FR-03 | 선택된 문서가 1건 이상이면 상단에 "N건 삭제" 버튼 표시 | High | Pending |
| FR-04 | 삭제 확인 다이얼로그에 삭제 대상 파일명 표시 | High | Pending |
| FR-05 | 삭제 완료 후 문서 목록 자동 새로고침 | High | Pending |
| FR-06 | 403 에러 시 "삭제 권한이 없습니다" 메시지 표시 | Medium | Pending |
| FR-07 | 일괄 삭제 부분 실패 시 성공/실패 건수 결과 표시 | Medium | Pending |
| FR-08 | 삭제 중 로딩 상태 표시 (버튼 비활성화 + 스피너) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| UX | 삭제 확인 없이 즉시 삭제되지 않을 것 | 다이얼로그 필수 경유 확인 |
| Performance | 삭제 후 목록 갱신 1초 이내 | invalidateQueries 즉시 호출 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 단건 삭제 API 연동 완료 (행별 삭제 버튼)
- [ ] 일괄 삭제 API 연동 완료 (체크박스 선택 + 삭제 버튼)
- [ ] 삭제 확인 다이얼로그 동작
- [ ] 에러 케이스 핸들링 (403, 404, 500)
- [ ] TDD 테스트 작성 및 통과
- [ ] 타입 안전성 확보 (type-check 통과)

### 4.2 Quality Criteria

- [ ] 훅/서비스 테스트 커버리지 80% 이상
- [ ] Zero lint errors
- [ ] Build succeeds

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| X-User-Id 헤더 미전송 시 백엔드 400/401 | High | Medium | authClient interceptor에서 자동 주입 |
| 일괄 삭제 부분 실패 시 UI 혼란 | Medium | Low | 성공/실패 건수 명확히 표시 + toast 메시지 |
| 대량 문서 삭제 시 응답 지연 | Low | Low | 로딩 스피너로 사용자 대기 유도 |

---

## 6. Architecture Considerations

### 6.1 Project Level

**Dynamic** — 기존 프로젝트 구조 유지 (React + TanStack Query + Zustand)

### 6.2 Key Architectural Decisions

| Decision | Selected | Rationale |
|----------|----------|-----------|
| API Client | authApiClient (axios) | 기존 인증 클라이언트에 X-User-Id 헤더 추가 |
| State Management | TanStack Query (useMutation) | 서버 상태 변경 → mutation 패턴 |
| 확인 UI | 공통 `ConfirmDialog` 컴포넌트 | title/description/variant를 props로 받아 삭제 외 확인 시나리오에도 재사용 |
| 체크박스 상태 | useState (로컬 상태) | 페이지 이동 시 초기화, 전역 불필요 |

### 6.3 구현 파일 목록

```
수정 대상:
├── src/constants/api.ts                           → 엔드포인트 상수 추가
├── src/types/collection.ts                        → 삭제 요청/응답 타입 추가
├── src/services/collectionService.ts              → deleteDocument, deleteDocuments 메서드
├── src/hooks/useCollections.ts                    → useDeleteDocument, useDeleteDocuments 훅
├── src/components/collection/DocumentTable.tsx    → 체크박스 + 삭제 핸들러 연결
├── src/components/collection/DeleteCollectionDialog.tsx → ConfirmDialog 사용으로 리팩터링
├── src/services/api/authClient.ts                 → X-User-Id 헤더 인터셉터 추가

신규 생성:
├── src/components/common/ConfirmDialog.tsx         → 공통 확인 다이얼로그 (variant: danger/warning/info)
```

---

## 7. Implementation Order

### Phase 1: 타입 & 상수 (기반)
1. `api.ts` — 엔드포인트 상수 추가
2. `collection.ts` — 삭제 요청/응답 타입 정의

### Phase 2: 서비스 & 훅
3. `authClient.ts` — X-User-Id 헤더 인터셉터
4. `collectionService.ts` — 삭제 API 메서드
5. `useCollections.ts` — mutation 훅

### Phase 3: 공통 컴포넌트
6. `ConfirmDialog.tsx` — 공통 확인 다이얼로그 (title, description, variant, confirmLabel props)
7. `DeleteCollectionDialog.tsx` — ConfirmDialog 기반으로 리팩터링 (기존 동작 유지)

### Phase 4: 문서 삭제 UI
8. `DocumentTable.tsx` — 체크박스 + 일괄 삭제 바 + 단건/일괄 삭제 핸들러 (ConfirmDialog 사용)

### Phase 5: 테스트
9. 훅/서비스 단위 테스트
10. ConfirmDialog 컴포넌트 테스트
11. DocumentTable 삭제 기능 테스트

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`/pdca design document-delete-api`)
2. [ ] 구현 시작 (`/pdca do document-delete-api`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-30 | Initial draft | 배상규 |
