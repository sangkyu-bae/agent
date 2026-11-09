# extractor-template-preview Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Completion Date**: 2026-11-09
> **PDCA Cycle**: Plan → Design → Do(3 모듈) → Check(98.6%, Act 없음) → Report

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | extractor-template-preview — 문서추출기 저장 양식 미리보기 |
| Start Date | 2026-11-08 |
| End Date | 2026-11-09 |
| Duration | 2일 |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 8/8)              │
├─────────────────────────────────────────────┤
│  ✅ Complete:     8 / 8 FR, SC 5 / 5         │
│  ⏳ 이월:         실데이터 확인 3건 (§4.1)    │
│  ❌ Cancelled:    0                          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 양식을 저장한 뒤 빌더 수정 화면에는 "✓ 양식 등록됨" 배지만 남고, 설정 모달은 빈 업로드 칸만 보여서 이 에이전트가 어떤 문서를 채우는지 알 수 없었다. |
| **Solution** | 저장된 `document_template`을 읽는 `GET /api/v1/agents/{agent_id}/document-template`을 추가하고, 빌더 배지와 설정 모달의 "저장된 양식 보기" 모드에서 이를 보여준다. 수정은 기존처럼 새 파일 교체로만 한다. |
| **Function/UX Effect** | 로컬 실데이터에서 배지가 `✓ 여신심의서 · 슬롯 23 · DOCX`로 바뀌었고, 모달에서 슬롯 23개의 위치가 라벨로 표시된 미리보기와 슬롯 목록을 확인했다. 교체 버튼을 누를 때만 업로드 화면으로 넘어간다. |
| **Core Value** | 소유자가 등록한 양식을 다시 확인할 수 있다. 포크로 양식을 물려받은 사용자에게는 원본 문서의 실제 값(예시값)을 서버에서 지워서 보낸다. |

---

## 1.4 Success Criteria Final Status

Plan v0.2 기준. SC-4 문구는 Design §1.2에 맞춰 "양식 원작자가 아니면 예시값 없음"으로 읽는다.

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | `?edit` 진입 시 배지에 저장 양식 이름 | ✅ Met | `LeftConfigPanel.tsx` `ExtractorSummaryBadge`; 테스트 F10; 실데이터 화면 |
| SC-2 | 모달에 미리보기·슬롯 목록, 슬롯 자리 라벨 하이라이트 | ✅ Met | `SavedTemplateView.tsx`; 테스트 F4(srcdoc 에 라벨, 토큰 없음); 실데이터 화면 |
| SC-3 | 교체 → 업로드 → 확정 → 저장이 기존과 같이 동작 | ✅ Met (정적·부분 실행) | 저장 경로 무변경, `agentBuilder.all` 무효화로 재조회. 교체 → 업로드 화면 → 보기 복귀는 화면 확인. 교체 후 실제 저장은 이번에 다시 실행하지 않음 |
| SC-4 | 양식 원작자가 아니면 응답에 예시값 없음 | ✅ Met (단위) | `TemplateSampleExposurePolicy`, 유스케이스; 테스트 B4·B5 |
| SC-5 | 권한 없음 403, 양식 없음 404 | ✅ Met | 라우터 테스트 B9; 실데이터 404·401 확인. 실제 타 사용자 403은 단위 테스트만 |

**Success Rate**: 5/5 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 노출 화면은 빌더 수정 화면만 | ✅ | 상세 응답·스토어·채팅 무변경 |
| [Plan] | 미리보기는 저장된 HTML 뼈대 + 슬롯 라벨 하이라이트 | ✅ | MCP 변환 호출 없음, 기존 `buildPreviewHtml` 확정 경로 재사용 |
| [Plan] | 수정은 보기 + 새 파일 교체 | ✅ | 조회 결과를 드래프트에 넣지 않아 원본 파일 id 만료 문제를 피함 |
| [Plan] | 타인에게는 예시값 숨김 (서버) | ✅ | 서버가 `sample_value`를 비우고 `samples_hidden=true` 표시 |
| [Design] | Option C — 별도 엔드포인트, 위저드 공용 패널 무수정 | ✅ | 위저드·기존 패널 회귀 0 |
| [Design] | 조회 키 = 워커 `tool_config.template_id` | ✅ | Design 조사에서 포크가 원작자 `template_id`를 공유하는 사실을 확인해 Plan 가정(agent_id 조회)을 바꿈 |
| [Design] | 예시값 기준 = 양식 원 에이전트 소유자, 권한 = `can_edit`(소유자), 관리자 예외 없음 | ✅ | Plan의 "편집자·관리자" 가정은 코드 사실(소유자 전용)과 달라 Design에서 정정 |
| [Do] | 모달 제목은 기존 "문서추출기 — 양식 등록" 유지 | ✅ (Design 변경) | 기존 테스트·접근성 이름 보존, Design v0.2 반영 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [extractor-template-preview.plan.md](../01-plan/features/extractor-template-preview.plan.md) | ✅ v0.2 |
| Design | [extractor-template-preview.design.md](../02-design/features/extractor-template-preview.design.md) | ✅ v0.2 |
| Check | [extractor-template-preview.analysis.md](../03-analysis/extractor-template-preview.analysis.md) | ✅ 98.6% |
| Act | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 저장 양식 조회 API | ✅ | 이름·포맷·skeleton·슬롯·`samples_hidden`·`is_inherited`·`updated_at` |
| FR-02 | 조회 권한 = 수정 권한, 403/404 | ✅ | 소유자 전용 (Design §1.2) |
| FR-03 | 비원작자 응답에서 예시값 제거 | ✅ | 기준: 양식 원 에이전트 소유자 |
| FR-04 | 저장 양식 있음 + 드래프트 없음일 때 조회 | ✅ | 드래프트가 있으면 요청하지 않음 (Check M2 테스트) |
| FR-05 | 배지에 이름·슬롯 수·포맷, 실패 시 기존 배지 | ✅ | |
| FR-06 | 모달 보기 모드 | ✅ | 라벨·예시값 공백 접기 포함 |
| FR-07 | 새 파일로 교체 ↔ 저장된 양식 보기 전환 | ✅ | |
| FR-08 | sandbox iframe + 폭 스케일 | ✅ | DOCX는 pt 폭이 없어 스케일 미적용 (§4.1) |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| Security | 비원작자 응답에 예시값 없음, sandbox 렌더링 | 서버 마스킹, `sandbox=""`, `source_file_ref`·`fill_hint` 비노출 | ✅ |
| Performance | 변환 호출 없이 DB 조회만 | 에이전트 조회 1~2회 + 템플릿 1회 | ✅ |
| Accessibility | iframe title, 버튼 이름, 상태 문구 role | `title="저장된 양식 미리보기"`, `role="status"`/`alert` | ✅ |
| Lint/Type | 새 오류 0 | 새 파일 ruff 0, 변경 파일 eslint·tsc 새 오류 0 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 도메인 정책 | `idt/src/domain/document_extractor/policies.py` (`TemplateSampleExposurePolicy`) | ✅ |
| 유스케이스 | `idt/src/application/agent_builder/get_agent_document_template_use_case.py` | ✅ |
| 응답 DTO | `idt/src/application/agent_builder/schemas.py` | ✅ |
| 라우트·DI | `idt/src/api/routes/agent_builder_router.py`, `idt/src/api/main.py` | ✅ |
| 프론트 계약 | `constants/api.ts`, `types/documentExtractor.ts`, `lib/queryKeys.ts`, `services/agentBuilderService.ts`, `hooks/useAgentBuilder.ts` | ✅ |
| UI | `components/agent-builder/SavedTemplateView.tsx`(신규), `DocumentExtractorConfigModal.tsx`, `LeftConfigPanel.tsx` | ✅ |
| 테스트 | 백엔드 3파일 20건, 프론트 신규 2파일 + 기존 3파일 보강 | ✅ |
| 문서 | Plan·Design·Analysis·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| 실제 타 사용자 계정으로 403 확인 | 로컬에 두 번째 사용자 로그인 시나리오를 준비하지 않음 (단위 테스트로 대체) | Low |
| 포크 사용자 실데이터 확인 (`is_inherited`, 예시값 숨김 화면) | 로컬 DB에 일회용 포크를 만들어야 함 (단위 테스트로 대체) | Medium |
| 교체 후 업로드·확정·저장 E2E | MCP 변환 도구 실행이 필요하고 저장 경로는 무변경이라 이번에 다시 돌리지 않음 | Low |
| DOCX 미리보기 좁은 화면 축소 | DOCX skeleton에는 pt 페이지 폭이 없음. 기존 업로드 패널도 같은 동작 | Low |

### 4.2 범위 밖 발견 (후속 사이클 후보)

| Item | 내용 | 영향 |
|------|------|------|
| 월 토큰이 `<style>`에 들어간 결함 | 로컬 "여신심의서" 양식의 `{{deliberation_date_month}}`가 본문이 아니라 `@page { size: 8.5in 11in }`에 들어가 있다. 확정 토큰화가 style 텍스트까지 매칭한 것으로 보인다 | 미리보기에서 월 자리가 "11"로 보임. 이 skeleton으로 채우면 페이지 크기가 깨질 수 있음 |
| 반복 예시값 원문 잔존 (Design §7) | `tokenizeHtml`은 예시값의 첫 출현만 토큰화한다. 같은 값이 여러 번 나오면 나머지는 skeleton에 원문으로 남는다 | 포크 사용자가 skeleton 본문에서 원본 값을 볼 수 있음 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | 90% | 98.6% (정적) / 97.3% (런타임 포함) |
| Critical / Important gap | 0 | 0 / 0 |
| 백엔드 신규 테스트 | 통과 | 20/20 |
| 백엔드 관련 회귀 | 신규 실패 0 | 1861 passed, 9 failed (전부 master 상시 실패 `test_agent_builder_router_stream`) |
| 프론트 신규·보강 테스트 | 통과 | 21건 통과 |
| 프론트 관련 회귀 | 신규 실패 0 | 111파일 1020/1020 (M2 테스트 추가 전), 추가 후 `LeftConfigPanel` 37/37 |

### 5.2 Resolved Issues (Check)

| Issue | Resolution |
|-------|------------|
| M1 미인증 테스트가 401·403 모두 허용 | 실측 401 확인 후 401 단일 단언 |
| M2 드래프트가 있을 때 무조회를 패널 수준에서 미검증 | MSW 호출 수 0 테스트 추가 |
| M3~M5 문서 불일치 (DI 함수명, 와이어프레임 제목, Plan 표현) | Design·Plan 수정 |
| 새 코드 ruff 경고 (줄 길이·import 정렬·미사용 import) | 정리 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- Design 단계에서 권한 정책과 포크 코드를 직접 읽어 Plan 가정 두 개(편집자·관리자 조회, agent_id 조회)를 구현 전에 바로잡았다.
- 조회 결과를 드래프트와 분리한 덕분에 위저드 공용 패널과 저장 경로를 건드리지 않았고, 관련 회귀가 0이었다.
- 실제 DB 데이터로 화면을 확인해서 단위 테스트로는 보이지 않는 두 가지(라벨 속 개행·탭, style 안의 토큰)를 찾았다.

### 6.2 What Needs Improvement (Problem)

- `SavedTemplateView`는 테스트를 먼저 썼지만 실패를 확인하기 전에 구현까지 작성했다. Red 확인 단계를 건너뛰었다.
- Check 전에 백엔드 ruff를 돌리지 않아 분석 단계에서 줄 길이 경고를 정리했다.

### 6.3 What to Try Next (Try)

- 화면을 다루는 사이클은 Do 단계 끝에 실데이터 확인을 고정 순서로 넣는다 (worktree 백엔드 8010 + vite 5175 + refresh 스텁).
- 변경 파일 ruff·eslint·tsc를 Do 완료 조건에 넣는다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 권한 범위를 사용자 답변으로 정함 | 권한·공유(포크) 관련 질문 전에 `VisibilityPolicy`와 fork 코드를 먼저 확인 |
| Do | 화면 확인 런처를 매번 새로 작성 | 런처 스크립트 3종을 프로젝트 도구로 남길지 검토 |
| Check | gap-detector가 이미 실행한 lint 결과를 몰랐다 | 위임할 때 실행한 검사 목록을 빠짐없이 전달 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] worktree 변경 커밋 → PR 생성 (브랜치 `feature/extractor-template-preview`)
- [ ] PR 머지 후 `/pdca archive extractor-template-preview` → worktree·junction 정리

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| 확정 토큰화가 `<style>`·`<head>` 텍스트를 매칭하지 않도록 수정 + 기존 저장 양식 점검 | High |
| 반복 예시값 전체 토큰화 또는 포크 시 skeleton 마스킹 | Medium |
| 스토어 상세·채팅 화면에서 양식 미리보기 (Plan 범위 밖으로 둔 항목) | Low |

---

## 9. Changelog

### extractor-template-preview (2026-11-09)

**Added:**
- `GET /api/v1/agents/{agent_id}/document-template` — 문서추출기 저장 양식 조회 (소유자 전용, 비원작자 예시값 제거)
- 빌더 문서추출기 설정 모달 "저장된 양식 보기" 모드 (미리보기·슬롯 목록·교체 버튼)

**Changed:**
- 문서추출기 도구 배지: "✓ 양식 등록됨" → "✓ {양식 이름} · 슬롯 N · {포맷}" (조회 실패 시 기존 문구)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-09 | Completion report created | 배상규 |
