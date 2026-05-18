# collection-department-dropdown Planning Document

> **Summary**: 컬렉션 생성/수정 시 부서 선택을 텍스트 입력(UUID)에서 서버 연동 드롭다운으로 변경
>
> **Project**: idt_front (RAG + AI Agent Frontend)
> **Author**: 배상규
> **Date**: 2026-05-08
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 컬렉션의 접근 범위를 '부서'로 설정할 때 부서 UUID를 직접 입력해야 하므로 사용성이 매우 떨어지고 오입력 위험이 높다 |
| **Solution** | 기존 부서 목록 API(`GET /api/v1/departments`)와 `useDepartments` 훅을 활용하여 드롭다운 셀렉트로 교체 |
| **Function/UX Effect** | 부서명이 표시되는 드롭다운에서 클릭 한 번으로 부서를 선택할 수 있어 입력 오류가 원천 차단된다 |
| **Core Value** | 기존 인프라(API + 훅) 재활용으로 최소 변경량으로 UX를 대폭 개선 |

---

## 1. Overview

### 1.1 Purpose

컬렉션 생성(`CreateCollectionModal`) 및 접근 범위 변경(`UpdateScopeModal`)에서 부서를 선택할 때, 사용자가 부서 UUID를 수동으로 입력하는 방식을 부서 목록 드롭다운으로 교체하여 사용성을 개선한다.

### 1.2 Background

- 현재 두 모달 모두 `scope === 'DEPARTMENT'`일 때 `<input type="text" placeholder="dept-uuid">` 형태로 부서 ID를 직접 입력받고 있다
- 사용자는 부서 UUID를 알 수 없으므로, 관리자 페이지에서 UUID를 복사해 와야 하는 번거로움이 있다
- 백엔드에 `GET /api/v1/departments` API가 이미 구현되어 있고, 프론트엔드에도 `useDepartments()` 훅과 `departmentService.getDepartments()`가 이미 존재한다
- 이 기존 인프라를 그대로 활용하면 최소한의 코드 변경으로 기능을 구현할 수 있다

### 1.3 Related Documents

- 관련 API: `idt/src/api/routes/department_router.py` — `GET /api/v1/departments`
- 기존 훅: `src/hooks/useDepartments.ts` — `useDepartments()`
- 기존 서비스: `src/services/departmentService.ts` — `getDepartments()`
- 기존 타입: `src/types/department.ts` — `Department { id, name, description }`

---

## 2. Scope

### 2.1 In Scope

- [x] `CreateCollectionModal.tsx` — 부서 텍스트 입력을 `<select>` 드롭다운으로 교체
- [x] `UpdateScopeModal.tsx` — 부서 텍스트 입력을 `<select>` 드롭다운으로 교체
- [x] 부서 목록 로딩 중/에러/빈 목록 상태 처리

### 2.2 Out of Scope

- 부서 관리 CRUD (이미 `AdminDepartmentsPage`에서 구현 완료)
- 부서 검색/필터 기능 (부서 수가 적어 불필요)
- 백엔드 API 변경 (기존 API 그대로 사용)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `CreateCollectionModal`에서 DEPARTMENT 선택 시 부서 드롭다운 표시 | High | Pending |
| FR-02 | `UpdateScopeModal`에서 DEPARTMENT 선택 시 부서 드롭다운 표시 | High | Pending |
| FR-03 | 드롭다운에 부서명(`name`) 표시, 선택 시 부서 ID(`id`) 전송 | High | Pending |
| FR-04 | 부서 목록이 비어있을 때 안내 메시지 표시 | Medium | Pending |
| FR-05 | 부서 목록 로딩 중 상태 표시 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 부서 목록 캐싱 (TanStack Query staleTime 활용) | 네트워크 탭 확인 |
| UX | 드롭다운이 기존 디자인 시스템과 일관성 유지 | 시각적 검토 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 두 모달에서 부서 텍스트 입력이 드롭다운으로 교체됨
- [ ] 부서 목록이 서버에서 정상 조회됨
- [ ] 부서 선택 시 올바른 `department_id`가 요청에 포함됨
- [ ] 빈 부서 목록/로딩/에러 상태가 처리됨

### 4.2 Quality Criteria

- [ ] TypeScript 타입 에러 없음
- [ ] 기존 테스트 통과
- [ ] 빌드 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 부서가 하나도 등록되지 않은 경우 | Medium | Medium | "등록된 부서가 없습니다" 안내 메시지 + DEPARTMENT 스코프 선택 비활성화 또는 경고 |
| 인증 토큰 없이 부서 API 호출 실패 | Low | Low | `useDepartments`가 `authClient` 사용하므로 인증 상태에서만 호출됨 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Dynamic** | Feature-based modules, TanStack Query, Zustand | **선택** |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 부서 데이터 조회 | 새 API 생성 / 기존 useDepartments 훅 재사용 | 기존 훅 재사용 | 이미 구현 완료되어 추가 작업 불필요 |
| UI 컴포넌트 | 커스텀 Combobox / 네이티브 select | 네이티브 select | 부서 수가 적고 기존 임베딩 모델 드롭다운과 동일 패턴 |

---

## 7. Implementation Guide

### 7.1 변경 대상 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/components/collection/CreateCollectionModal.tsx` | 204-217행 부서 ID 텍스트 입력을 `<select>` 드롭다운으로 교체, `useDepartments` import 추가 |
| `src/components/collection/UpdateScopeModal.tsx` | 103-116행 부서 ID 텍스트 입력을 `<select>` 드롭다운으로 교체, `useDepartments` import 추가 |

### 7.2 변경 패턴 (Before → After)

**Before** (두 모달 공통):
```tsx
<input
  type="text"
  value={departmentId}
  onChange={(e) => setDepartmentId(e.target.value)}
  placeholder="dept-uuid"
  className="w-full rounded-xl border border-zinc-300 ..."
/>
```

**After**:
```tsx
const { data: deptData, isLoading: isDeptLoading } = useDepartments();

// ...

<select
  value={departmentId}
  onChange={(e) => setDepartmentId(e.target.value)}
  className="w-full rounded-xl border border-zinc-300 ..."
>
  <option value="">부서를 선택하세요</option>
  {deptData?.map((dept) => (
    <option key={dept.id} value={dept.id}>
      {dept.name}
    </option>
  ))}
</select>
```

### 7.3 의존성

- 신규 패키지 설치: **없음**
- 기존 활용: `useDepartments()` from `@/hooks/useDepartments`

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`collection-department-dropdown.design.md`)
2. [ ] 구현 (모달 2개 수정)
3. [ ] 수동 테스트 (부서 선택 → 컬렉션 생성 확인)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-08 | Initial draft | 배상규 |
