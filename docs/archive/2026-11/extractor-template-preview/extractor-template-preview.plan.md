# extractor-template-preview Planning Document

> **Summary**: 문서추출기(양식 채우기) 도구에 저장된 양식을 빌더 수정 화면에서 이름·미리보기·슬롯 목록으로 다시 볼 수 있게 한다
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-08
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 양식을 등록하고 에이전트를 저장한 뒤 빌더 수정 화면으로 돌아오면 "✓ 양식 등록됨" 배지만 보인다. 설정 모달을 열면 빈 업로드 칸만 나와서, 작성자도 다른 편집자도 이 에이전트가 어떤 문서를 채우는지 알 수 없다. |
| **Solution** | 저장된 양식(이름·`html_skeleton`·슬롯)을 읽는 조회 API를 추가한다. 빌더는 배지에 양식 이름을 표시하고, 설정 모달에서 저장된 양식의 미리보기(슬롯 라벨 하이라이트)와 슬롯 목록을 보여준다. 수정은 기존과 같이 새 파일로 교체한다. |
| **Function/UX Effect** | 수정 화면에 들어오면 "어떤 양식의 어느 칸을 채우는지"를 바로 확인할 수 있다. 교체가 필요할 때만 업로드 화면으로 전환한다. |
| **Core Value** | 에이전트 소유자(P2)가 등록한 양식을 다시 확인하고, 공동 편집자에게 인계할 수 있다. 원본 문서의 실제 값(예시값)은 소유자와 관리자에게만 노출한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 저장 후 양식이 "등록됨" 배지로만 남아 어떤 문서를 만드는 에이전트인지 확인할 수 없다 |
| **WHO** | 에이전트 소유자(P2), 같은 에이전트를 수정할 수 있는 편집자·관리자 |
| **RISK** | 슬롯 예시값(sample_value)에 원본 문서의 실명·금액이 들어 있어, 조회 API가 편집자에게 그대로 노출할 수 있다 |
| **SUCCESS** | `?edit` 진입 시 배지에 양식 이름 표시, 모달에서 저장된 양식 미리보기·슬롯 목록 표시, 비소유자 응답에 예시값 없음 |
| **SCOPE** | 백엔드 조회 API 1개 + 프론트 서비스·훅·배지·모달 보기 모드. 스토어·채팅 화면 노출과 저장 양식 직접 편집은 제외 |

---

## 1. Overview

### 1.1 Purpose

문서추출기 도구에 저장된 양식을 빌더 수정 화면에서 다시 확인할 수 있게 한다.

### 1.2 Background

현재 동작(코드 확인 결과):

- 양식은 확정 시 `document_template` 테이블(V037)에 `name`, `html_skeleton`(`{{slot_key}}` 토큰 포함), `slots`(JSON), `source_file_ref`, `source_format`으로 저장된다.
- 에이전트 상세 응답에는 추출기 워커의 `tool_config.template_id`만 들어 있고, 템플릿 본문을 읽는 API가 없다.
- 프론트는 `savedTemplateIdFromWorkers()`로 id 존재 여부만 확인한다(`idt_front/src/utils/agentDetailMapping.ts:110`). 드래프트로 되돌리지 않는 이유는 원본 업로드 파일 id가 만료돼 재저장이 실패하기 때문이다(wizard-template-request Act-1 G3).
- 그 결과 배지는 "✓ 양식 등록됨"만 표시하고(`LeftConfigPanel.tsx:852`), 모달은 빈 업로드 칸과 `FORM_TEMPLATE_REPLACE_NOTICE`만 보여준다.

`buildPreviewHtml()`(`idt_front/src/utils/documentTemplate.ts`)은 이미 확정된 skeleton의 `{{key}}` 토큰을 라벨 하이라이트로 바꾸는 경로를 갖고 있어, 저장된 skeleton을 그대로 재사용할 수 있다.

### 1.3 Related Documents

- `docs/archive/2026-11/wizard-template-request/` — 저장 양식 "존재 표시"만 한 결정(G3)
- docx-format-preserving-fill (PR #105~#107) — 원본 docx 직접 채움
- `docs/wiki/backend/api/router-map.md` — document_extractor 라우터 구성

---

## 2. Scope

### 2.1 In Scope

- [ ] 백엔드: 에이전트에 저장된 활성 양식을 읽는 조회 API (이름·포맷·skeleton·슬롯·등록일)
- [ ] 백엔드: 소유자·관리자가 아니면 응답에서 `sample_value`를 비운다
- [ ] 프론트: 엔드포인트 상수·타입·서비스·TanStack Query 훅 (`queryKeys` 팩토리 등록)
- [ ] 프론트: 추출기 요약 배지에 양식 이름과 슬롯 수 표시 (`✓ {양식 이름} · 슬롯 N · DOCX`)
- [ ] 프론트: 설정 모달 "저장된 양식 보기" 모드 — 미리보기 iframe(sandbox, 라벨 하이라이트) + 슬롯 목록(읽기 전용) + "새 파일로 교체" 버튼
- [ ] 교체 버튼을 누르면 기존 업로드 흐름으로 전환. 새 드래프트가 생기면 드래프트가 우선한다(현재 저장 로직 유지)
- [ ] 조회 실패·양식 없음 상태 표시 (기존 "양식 등록됨"/"미등록" 배지로 폴백)

### 2.2 Out of Scope

- 에이전트 스토어 상세 팝업·채팅 화면에서의 미리보기 (이번 사이클은 빌더 수정 화면만)
- 저장된 양식의 슬롯 라벨 수정·삭제 (교체는 새 파일 업로드로만)
- 원본 docx/pdf 재변환 미리보기 (MCP 호출 없이 저장된 skeleton만 사용)
- 원본 파일 다운로드

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 에이전트 id로 활성 양식(이름·source_format·html_skeleton·slots·updated_at)을 조회하는 API를 제공한다 | High | Pending |
| FR-02 | 조회 권한은 해당 에이전트를 수정할 수 있는 사용자(`VisibilityPolicy.can_edit`)로 제한한다. 권한이 없으면 403, 에이전트나 활성 양식이 없으면 404 | High | Pending |
| FR-03 | 요청자가 소유자 또는 관리자가 아니면 각 슬롯의 `sample_value`를 빈 문자열로 보낸다 | High | Pending |
| FR-04 | 빌더 수정 화면에서 `savedTemplateId`가 있고 드래프트가 없으면 양식을 조회한다 | High | Pending |
| FR-05 | 추출기 배지에 양식 이름·슬롯 수·포맷을 표시한다. 조회 전·실패 시 기존 "✓ 양식 등록됨"으로 폴백한다 | High | Pending |
| FR-06 | 설정 모달은 저장 양식이 있고 드래프트가 없을 때 보기 모드로 연다: 양식 이름, 미리보기(라벨 하이라이트), 슬롯 목록(유형 배지·라벨·예시값이 있으면 예시값) | High | Pending |
| FR-07 | 보기 모드의 "새 파일로 교체" 버튼은 업로드 화면으로 전환하고, 교체 안내(`FORM_TEMPLATE_REPLACE_NOTICE`)를 유지한다. 업로드 전에 취소하면 보기 모드로 돌아간다 | Medium | Pending |
| FR-08 | 미리보기는 기존과 같이 `sandbox=""` iframe과 컨테이너 폭 스케일을 쓴다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | 비소유자 응답 JSON에 `sample_value` 원문이 없다. 미리보기 HTML은 sandbox iframe으로만 렌더링한다 | 라우터 테스트(권한별 응답), 컴포넌트 테스트 |
| Performance | 조회는 DB 1회(에이전트 + 템플릿), 변환 호출 없음 | 코드 리뷰 |
| Accessibility | iframe `title`, 버튼 이름, 상태 문구 `role="status"` | RTL 쿼리 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: `?edit`로 진입하면 배지에 저장된 양식 이름이 표시된다
- [ ] SC-2: 설정 모달에서 저장 양식의 미리보기와 슬롯 목록이 보이고, 슬롯 자리에 라벨이 하이라이트된다
- [ ] SC-3: "새 파일로 교체" → 업로드 → 확정 → 저장 흐름이 기존과 같이 동작한다
- [ ] SC-4: 소유자·관리자가 아닌 편집자의 응답에 `sample_value`가 비어 있다
- [ ] SC-5: 권한 없는 사용자 403, 양식 없는 에이전트 404
- [ ] 백엔드 pytest·프론트 Vitest 테스트 선작성(TDD) 후 통과

### 4.2 Quality Criteria

- [ ] 변경 범위 lint·type-check 오류 0 (master 기준 대비 신규 오류 없음)
- [ ] 백엔드 관련 테스트 묶음 회귀 통과
- [ ] 프론트 `agent-builder` 컴포넌트·훅 테스트 회귀 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `sample_value`에 원본 문서의 실명·금액이 있어 편집자에게 노출 | High | High | FR-03: 서버에서 비소유자 응답의 예시값을 지운다. 프론트 마스킹에 의존하지 않는다 |
| `html_skeleton`의 슬롯 외 본문에도 원본 문서의 고정 내용이 남아 있다 | Medium | Medium | 편집 권한자만 조회(FR-02). 슬롯 외 본문은 양식 자체 내용이므로 그대로 보여준다고 Plan에서 확정 |
| skeleton 미리보기와 docx 직접 채움 결과의 서식이 다를 수 있다 | Low | Medium | 미리보기는 "채울 위치 확인용"이라는 안내 문구를 둔다 |
| 조회 데이터를 드래프트로 바꿔 재저장하면 만료된 원본 파일 id로 실패 | High | Low | 조회 결과는 `documentExtractorDraft`에 넣지 않고 별도 읽기 전용 상태로만 쓴다 |
| 큰 skeleton(LONGTEXT)으로 응답이 무거움 | Low | Low | 모달이 열리거나 배지가 렌더될 때만 조회, staleTime 기본값 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| document_extractor 또는 agent_builder 라우터 | API | 저장 양식 조회 GET 엔드포인트 추가 (경로는 Design에서 결정) |
| `DocumentTemplateRepositoryInterface.find_active_by_agent_worker` | Repository | 기존 메서드 재사용 (변경 없음 예상) |
| `LeftConfigPanel` `ExtractorSummaryBadge` | UI | 양식 이름 표시 |
| `DocumentExtractorConfigModal` / `DocumentExtractorConfigPanel` | UI | 저장 양식 보기 모드 추가 |
| `constants/api.ts`, `types/documentExtractor.ts`, `services`, `hooks/useDocumentExtractor.ts`, `lib/queryKeys.ts` | Front | 조회 계약 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| document_template | READ | `composer.py` `_replace_tokens` (런타임 채움) | None — 조회 API는 읽기만 한다 |
| document_template | CREATE/DELETE | 에이전트 생성·수정 시 템플릿 저장/soft-delete | None |
| `savedTemplateId` | READ | `agentDetailMapping.ts`, `LeftConfigPanel` 배지·모달 안내 | Needs verification — 배지 분기 확장 |
| `DocumentExtractorConfigPanel` | RENDER | 스튜디오 모달, 위저드 `DocumentsStep` | Needs verification — 보기 모드는 저장 양식이 있을 때만 켜지게 해서 위저드(신규 생성)에는 영향 없음 |
| `documentExtractorDraft` sessionStorage 복원 | READ/WRITE | `LeftConfigPanel` R4 | None — 조회 결과를 드래프트에 넣지 않는다 |

### 6.3 Verification

- [ ] 위저드 신규 생성 흐름(양식 업로드→확정→생성) 회귀
- [ ] 수정 화면에서 교체 없이 저장 시 기존 template_id 유지
- [ ] 교체 후 저장 시 새 템플릿 저장·기존 soft-delete

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| **Enterprise** (DDD 레이어 분리 — idt/ 규칙) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 미리보기 소스 | 저장 skeleton / 원본 재변환 / 목록만 | 저장 skeleton + 라벨 하이라이트 | 이미 저장돼 있고 MCP 호출이 없다. `buildPreviewHtml` 재사용 |
| 수정 방식 | 보기+교체 / 저장 양식 직접 편집 | 보기+교체 | 원본 파일 id 만료 문제를 피하고 저장 API를 바꾸지 않는다 |
| 예시값 노출 | 타인 숨김 / 모두 공개 / 미리보기 소유자만 | 소유자·관리자 외 숨김(서버) | 원본 문서 실값 보호 |
| 노출 화면 | 빌더 / 스토어 / 채팅 | 빌더 수정 화면만 | 이번 사이클 범위 축소 |
| 조회 키 | agent_id / template_id | Design에서 결정 (agent_id 기준이 권한 검사에 유리) | — |
| 서버 상태 | TanStack Query | `useQuery` + `queryKeys` 팩토리 | 프론트 규칙 |

### 7.3 Clean Architecture Approach

```
idt/ : api/routes → application(UseCase: 권한·마스킹) → domain(interfaces/policies) → infrastructure(repository)
idt_front/ : constants/api.ts → types → services → hooks(useQuery) → components/agent-builder
```

---

## 8. Convention Prerequisites

- 백엔드: `idt/CLAUDE.md`, `idt/docs/rules/` (TDD, 레이어 규칙, 로깅 request_id)
- 프론트: `idt_front/CLAUDE.md` (queryKeys 팩토리, 컴포넌트 파일 런타임 상수 export 금지 → `src/types/*.ts`, 디자인 토큰)
- API 계약 동기화: 루트 CLAUDE.md §4-1 (`/api-contract-sync`)
- 환경변수 추가 없음

---

## 9. Next Steps

1. [ ] `/pdca design extractor-template-preview` — 엔드포인트 경로·응답 스키마·보기 모드 상태 전이 확정
2. [ ] 구현 (worktree 분리, TDD)
3. [ ] `/pdca analyze extractor-template-preview`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-08 | Initial draft (노출 위치·미리보기·수정 방식·예시값 정책 사용자 확정) | 배상규 |
| 0.2 | 2026-11-08 | Design 조사 반영: can_edit은 소유자 전용(관리자 제외), 포크는 원작자 template_id 공유 → FR-02/FR-03·Executive Summary·Context Anchor·SC-4·§6.1의 '편집자·관리자' 표현은 Design §1.2 기준(조회 키 template_id, 권한은 소유자, 예시값은 양식 원 에이전트 소유자만)으로 대체. 훅 위치는 Design §9(useAgentBuilder.ts) | 배상규 |
