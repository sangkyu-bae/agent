# extractor-template-preview Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: sangplusbot (Agent Builder)
> **Analyst**: 배상규 (gap-detector 정적 분석 + 세션 내 런타임 확인)
> **Date**: 2026-11-09
> **Design Doc**: [extractor-template-preview.design.md](../02-design/features/extractor-template-preview.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 저장 후 양식이 "등록됨" 배지로만 남아 어떤 문서를 만드는 에이전트인지 확인할 수 없다 |
| **WHO** | 에이전트 소유자(P2). 포크로 양식을 물려받은 사용자 포함 |
| **RISK** | 슬롯 예시값(sample_value)에 원본 문서의 실명·금액이 들어 있고, 포크 에이전트는 원작자 양식을 공유한다 |
| **SUCCESS** | `?edit` 진입 시 배지에 양식 이름 표시, 모달에서 저장 양식 미리보기·슬롯 목록 표시, 양식 원작자가 아니면 응답에 예시값 없음 |
| **SCOPE** | 백엔드 조회 API 1개 + 프론트 서비스·훅·배지·모달 보기 모드. 스토어·채팅 노출과 저장 양식 직접 편집 제외 |

---

## Strategic Alignment Check

PRD 없음(`docs/00-pm/` 미작성). Plan·Design 기준으로 판정한다.

| 항목 | 기대 | 결과 |
|------|------|:----:|
| 핵심 문제 (WHY) | 수정 화면에서 어떤 양식인지 알 수 있어야 한다 | ✅ 배지에 이름, 모달에 미리보기·슬롯 목록 |
| 대상 (WHO) | 소유자, 포크 사용자 | ✅ 소유자 조회, 포크 사용자는 예시값 없이 조회 |
| 보호 (RISK) | 원본 실값 비노출 | ✅ 서버에서 예시값을 지움 (단위 테스트) |

### Success Criteria Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | `?edit` 진입 시 배지에 저장 양식 이름 | ✅ | `LeftConfigPanel.tsx:152-157`, `:878-884`; 테스트 F10; 실데이터 화면 `✓ 여신심의서 · 슬롯 23 · DOCX` |
| SC-2 | 모달에 미리보기·슬롯 목록, 슬롯 자리에 라벨 하이라이트 | ✅ | `SavedTemplateView.tsx`; 테스트 F4(srcdoc 에 라벨, 토큰 없음); 실데이터 화면 |
| SC-3 | 교체 → 업로드 → 확정 → 저장이 기존과 같이 동작 | ✅ (정적) | 드래프트·저장 경로 무변경, `agentBuilder.all` 무효화로 재조회; 교체→업로드→복귀는 화면 확인. 교체 후 저장 E2E 는 이번 사이클에 다시 돌리지 않음 |
| SC-4 | 양식 원작자가 아니면 응답에 예시값 없음 (Design §1.2 기준) | ✅ (단위) | 유스케이스 `:82-104`, 정책; 테스트 B4·B5. 실데이터 포크 시나리오 미실행 |
| SC-5 | 권한 없음 403, 양식 없음 404 | ✅ | 라우터 테스트 B9; 실데이터 404·401 확인. 실제 타 사용자 403 은 단위 테스트만 |

**Success Rate**: 5/5

### Decision Record Verification

| Source | Decision | Followed? | 근거 |
|--------|----------|:---------:|------|
| [Plan] | 빌더 수정 화면만, 저장 skeleton 미리보기, 보기+교체 | ✅ | 스토어·채팅·상세 응답 무변경 |
| [Design] | Option C (별도 엔드포인트, 위저드 공용 패널 무수정) | ✅ | `GetAgentResponse`·`DocumentExtractorConfigPanel.tsx` 무변경 |
| [Design] | 조회 키 = 워커 `tool_config.template_id` | ✅ | 유스케이스 `_extractor_template_id` |
| [Design] | 예시값 = 양식 원 에이전트 소유자만 | ✅ | `TemplateSampleExposurePolicy` |
| [Design] | 권한 = `can_edit`(소유자), 관리자 예외 없음 | ✅ | 테스트 `test_admin_who_is_not_owner_is_rejected` |
| [Design] | 조회 결과를 드래프트에 넣지 않음 | ✅ | 드래프트 쓰기는 패널 `onChange` 한 곳뿐 |

---

## 1. Analysis Overview

- **Design Document**: `docs/02-design/features/extractor-template-preview.design.md` (v0.2)
- **Implementation Path**: worktree `wt/extractor-template-preview` — `idt/` 백엔드 5파일(신규 1), `idt_front/src` 8파일(신규 1) + 테스트
- **Analysis Date**: 2026-11-09

---

## 2. Gap Analysis

### 2.1 API Endpoints

| Design | Implementation | Status |
|--------|---------------|--------|
| GET `/api/v1/agents/{agent_id}/document-template` | `agent_builder_router.py` `get_agent_document_template` | ✅ Match |

### 2.2 Data Model (응답 DTO)

| Field | Design | Backend | Frontend | Status |
|-------|--------|---------|----------|:------:|
| template_id, name, html_skeleton | str | str | string | ✅ |
| source_format | "pdf"\|"docx" | str | `'pdf' \| 'docx'` | ✅ |
| slots[] (key, label, slot_type, description, sample_value) | 동일 | 동일 | 동일 | ✅ |
| samples_hidden, is_inherited | bool | bool | boolean | ✅ |
| updated_at | datetime | datetime | string (ISO) | ✅ |
| source_file_ref, fill_hint | 비노출 | 없음 | 없음 | ✅ |

### 2.3 Component Structure

| Design Component | Implementation | Status |
|------------------|----------------|:------:|
| SavedTemplateView (신규) | `components/agent-builder/SavedTemplateView.tsx` | ✅ |
| DocumentExtractorConfigModal (보기/업로드 모드) | 같은 폴더 | ✅ |
| LeftConfigPanel (조회 1회, 배지·모달 전달) | 같은 폴더 | ✅ |
| ExtractorSummaryBadge (이름·슬롯 수·포맷) | `LeftConfigPanel.tsx` 내부 | ✅ |

### 2.4 Functional Depth

Shallow 파일 0. placeholder·mock 데이터 없음. §4.2 처리 순서 6/6, §6 오류 처리 4/4, §7 보안 4/4 (5번째 잔여 위험은 설계상 범위 밖).

### 2.5 Page UI Checklist (§5.4)

| 화면 | Design | 구현 | 누락 | Rate |
|------|:------:|:----:|:----:|:----:|
| 도구 목록 배지 | 3 | 3 | 0 | 100% |
| 모달 saved 모드 | 10 | 10 | 0 | 100% |
| 모달 upload 모드 | 2 | 2 | 0 | 100% |

### 2.6 API Contract (3-way)

| # | Endpoint | Design | Server | Client | Contract |
|---|----------|:------:|:------:|:------:|:--------:|
| 1 | GET document-template | ✅ | ✅ | ✅ (404→null, 그 외 전파) | PASS |

**Contract Match Rate**: 1/1 = 100%

### 2.7 Runtime Verification

#### L1: API (인프로세스 TestClient + 로컬 DB, 서버 8010)

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | 소유자 조회 (여신심의서) | 200 + 슬롯·예시값 | 200, 슬롯 23 | ✅ |
| 2 | 없는 에이전트 | 404 "Agent not found" | 404 | ✅ |
| 3 | 토큰 없음 | 401 | 401 | ✅ |
| 4 | 타 사용자 | 403 | 미실행 (DB 에 없는 user id 는 401 "User not found") | — |

#### L2: UI (Chrome, worktree vite 5175 + 백엔드 8010)

| # | Action | Expected | Pass |
|---|--------|----------|:----:|
| 1 | `?edit` 진입 | 배지 `✓ 여신심의서 · 슬롯 23 · DOCX` | ✅ |
| 2 | 문서추출기 설정 클릭 | 저장된 양식 보기, 라벨 하이라이트 미리보기, 슬롯 목록(공백 접힘) | ✅ |
| 3 | 새 파일로 교체 | 업로드 화면 + 교체 안내 + "저장된 양식 보기" | ✅ |
| 4 | 375px 폭 | 모달·배지 깨짐 없음 | ✅ |

#### L3: E2E

교체 후 실제 업로드·확정·저장, 포크 사용자 시나리오는 미실행 (Report 이월 항목).

**자동 테스트**: 백엔드 신규 20건 통과, 관련 묶음 1861 passed / 9 failed(전부 `test_agent_builder_router_stream`, master 상시 실패). 프론트 신규 21건 통과, 관련 디렉터리 111파일 1020건 통과(M2 테스트 추가 전 기준, 추가 후 해당 파일 37건 통과).

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  98%                 │
│  Functional Match Rate:  98%                 │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:     ~90% (L1 3/4, L2 4/4, L3 미실행) │
│  ─────────────────────────────────────────── │
│  Overall (정적, gap-detector v2.1.1): 98.6%  │
│  Overall (런타임 포함):               97.3%  │
└─────────────────────────────────────────────┘
```

---

## 3. Gap 목록과 처리

Critical 0 · Important 0 · Minor 5. 이번 Check 에서 모두 반영했다.

| # | Gap | 처리 |
|---|-----|------|
| M1 | 라우터 미인증 테스트가 `(401, 403)` 을 모두 허용 | 401 단일 단언으로 수정 (실측 401 확인) |
| M2 | "드래프트가 있으면 조회 안 함" 을 패널 수준에서 검증하지 않음 | `LeftConfigPanel.test.tsx` 에 MSW 호출 수 0 단언 테스트 추가 |
| M3 | Design §4.1/§9 의 DI 위치(`create_agent_builder_factories`)와 실제(`create_agent_document_template_factory`) 불일치 | Design 수정 |
| M4 | Design §5.1 와이어프레임 제목이 "문서추출기 — 양식" | "양식 등록" 으로 수정 |
| M5 | Plan 의 "편집자·관리자" 표현이 v0.2 대체 범위 밖에 남음 | Plan v0.2 이력에 대체 범위를 넓혀 명시 |

추가로 ruff 에서 새 코드의 줄 길이·import 정렬·미사용 import 를 정리했다 (새 파일 ruff 0건).

---

## 4. 범위 밖 발견 사항 (수정하지 않음)

| # | 내용 | 영향 |
|---|------|------|
| X1 | 여신심의서 양식의 `{{deliberation_date_month}}` 토큰이 본문이 아니라 `<style>@page { size: 8.5in 11in }` 에 들어가 있다. 확정 토큰화가 style 텍스트를 매칭한 것으로 보인다 | 미리보기에서 월 자리가 라벨 대신 "11" 로 보임. 이 skeleton 으로 채우면 페이지 크기가 깨질 수 있음 |
| X2 | DOCX skeleton 에는 pt 페이지 폭이 없어 좁은 화면에서 미리보기가 축소되지 않는다 | iframe 안 가로 스크롤 (기존 업로드 패널과 동일) |
| X3 | Design §7 잔여 위험: `tokenizeHtml` 은 예시값 첫 출현만 토큰화 → 반복 값은 skeleton 에 원문으로 남아 포크 사용자에게 보인다 | 별도 사이클 후보 |

---

## 5. Test Coverage (시나리오 매핑)

Design §8.2 B1–B10, §8.3 F1–F11 전부 대응 테스트가 있다 (gap-detector 매핑 확인).

---

## 6. Clean Architecture Compliance

| Layer | 파일 | 의존 | Status |
|-------|------|------|:------:|
| Domain | `policies.py` `TemplateSampleExposurePolicy` | 외부 의존 없음 | ✅ |
| Application | `get_agent_document_template_use_case.py` | domain 인터페이스·정책만 | ✅ |
| Interface | 라우터·`main.py` DI | application | ✅ |
| Front | constants → types → services → hooks → components | 컴포넌트에서 axios 직접 호출 없음, 문구 상수는 `types/` | ✅ |

---

## 7. Next Steps

- [x] Minor M1–M5 반영
- [ ] Report 작성 (`/pdca report extractor-template-preview`) — X1·X3 를 후속 후보로, L3 미실행 항목을 이월로 기록

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-09 | Initial analysis (98.6%), Minor 5건 즉시 반영 | 배상규 |
