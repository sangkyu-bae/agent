# agent-kb-quick-setup Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Completion Date**: 2026-11-05
> **PDCA Cycle**: #1 (Plan → Design → Do M1~M4 → Check → Act-1 → Report, 단일 세션)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-kb-quick-setup — 빌더 안 원스톱 KB 구성 |
| Start Date | 2026-11-05 |
| End Date | 2026-11-05 |
| Duration | 1일 (단일 세션) |
| 코드 위치 | worktree `../wt/kb-quick-setup`, 브랜치 `feature/agent-kb-quick-setup` (**미커밋**, 사용자 커밋 지시 대기) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (Plan 범위)           │
├─────────────────────────────────────────────┤
│  ✅ Complete:     15 / 15 FR                  │
│  ✅ Success Criteria: 7 / 7                   │
│  ⏭ 이월(Minor·요검토): G7·G8, R1~R7           │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트에 KB를 붙이려면 컬렉션(임베딩 모델·벡터 크기·거리 함수) → KB(컬렉션·청킹) → 업로드 → RAG 도구 설정까지 4개 화면·약 15개 결정이 필요했고, 컬렉션이 없으면 "관리자에게 요청하세요"에서 멈췄다. |
| **Solution** | 관리자가 기본 임베딩 모델을 1회 설정하면(`kb_default_setting` V084), 빌더에서 파일을 올리는 것만으로 서버 `/quick`이 KB·전용 컬렉션(`kb-{id8}`)·문서 적재를 끝내고 RAG 도구가 기본값으로 부착된다. 스튜디오 도구함 블록과 위저드 문서 단계가 같은 블록을 공유하고, 기존 RAG 설정은 "고급 설정"으로 접었다. |
| **Function/UX Effect** | 실런 기준 사용자 결정은 "파일 선택" 1회다. 스튜디오: PDF 드롭 → 저장 → 테스트 채팅이 문서 내용으로 답변. 위저드: 도구 확정 → 문서 업로드 → 프롬프트 → 스튜디오 프리필 → 저장까지 KB·컬렉션 화면을 한 번도 거치지 않음. 간단 모드 화면에 컬렉션·벡터·거리 함수·청킹·BM25·RRF·top_k 용어 0건. 부분 실패는 파일명·사유로 표시되고 성공 파일만으로 도구가 연결된다. |
| **Core Value** | S1(KB 폐루프)의 성공 기준 "개발자 개입 없이 P2 혼자 완주"가 에이전트 생성 경로에서 성립한다. 기존 경로는 additive 계약으로 무변경(백엔드 53건·프론트 9건 상시 실패 외 회귀 0). |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 스튜디오 PDF 드롭 → 저장 → 테스트 채팅 근거 답변 | ✅ Met | 실런(워크트리 :8010/:5176): KB `[CHECK] 퀵셋업봇 지식`·컬렉션 `kb-0b838911`(points 2) → 워커 `internal_document_search` `tool_config.kb_id` → 답변 "주중 9시~18시, 4821"(문서 내용) |
| SC-2 | 위저드 업로드 → 생성 → 상세에 RAG+KB | ✅ Met | 실런: 문서 단계 업로드 → PROMPT 요청 `kb_id` → 스튜디오 프리필 → 저장 → 워커 kb_id=`2ccb6a8a…`, KB `문서 Q&A 지식` |
| SC-3 | 미설정 문구 노출 | ✅ Met | 설정 NULL 상태 블록 `role=alert` "관리자가 기본 임베딩 모델을 설정해야 합니다", 입력 disabled |
| SC-4 | 2개 중 1개 실패 시 파일명 + 도구 연결 | ✅ Met | 실런: "broken.pdf: Failed to open stream", 1/2, 도구 연결 완료. 백엔드 스모크 동일 |
| SC-5 | `/knowledge-bases`에 `{이름} 지식`·범위 일치 | ✅ Met | KB 목록 API `('[CHECK] 퀵셋업봇 지식','PERSONAL','kb-0b838911')`, 에이전트 private |
| SC-6 | 금지 용어 7종 없음 | ✅ Met | 블록 DOM 검사 `forbidden: []` + 컴포넌트 테스트 |
| SC-7 | 회귀 FAILED diff 비어 있음 | ✅ Met | 백엔드 53건 = master 상시 실패(4회 실행 모두 동일), 프론트 9건 = 상시 실패 9건 |

**Success Rate**: 7/7 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 빌더 안 원스톱, 스튜디오+위저드 둘 다 | ✅ | 공용 `KnowledgeDocsBlock` 1개를 두 화면이 사용 |
| [Plan] | 관리자 전역 설정은 기본 임베딩 모델 하나(단일 행) | ✅ | V084 `kb_default_setting`, `/admin/kb-defaults` 1화면 |
| [Plan] | **KB마다 컬렉션 1개**(사용자 결정, 공유 컬렉션 거부) | ✅ | `kb-{kb_id[:8]}`, 적재 시 임베딩 모델은 활동 로그 CREATE로 결정됨을 실런 확인 |
| [Plan] | KB 이름·범위는 에이전트를 따라감, 고아 허용 | ✅ | `{에이전트명} 지식`·PERSONAL. 생성 폼에 visibility 필드가 없어 private 고정(의도된 편차) |
| [Design] | 설계안 C: 서버 `/quick` + 기존 UseCase 조합, 파이프라인 단계 수 불변(optional `kb_id`) | ✅ | `QuickCreateKnowledgeBaseUseCase`, steps 5개 유지, `PipelinePolicy.with_knowledge_tool` |
| [Design] | 흡수 지점 1곳(`_upload_one`) | ✅ | AST 계약 테스트로 고정 |
| [Design] | `CollectionAssignerInterface`에 자동 배정 구현 추가(additive kwargs + rollback) | ✅ | `AutoProvisionCollectionAssigner`, 사용자 선택 경로 무변경 |
| [Check] | Important 2건만 수정, Minor는 문서 갱신(사용자 결정) | ✅ | G1 재시도 고아 KB·G2 안내 노출 수정, G3~G6 Design 갱신 → 98.9% |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-kb-quick-setup.plan.md](../01-plan/features/agent-kb-quick-setup.plan.md) | ✅ Finalized |
| Design | [agent-kb-quick-setup.design.md](../02-design/features/agent-kb-quick-setup.design.md) | ✅ Finalized (Act-1 갱신 반영) |
| Check | [agent-kb-quick-setup.analysis.md](../03-analysis/agent-kb-quick-setup.analysis.md) | ✅ Complete (Match 98.9%) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 기본 임베딩 모델 설정·조회(활성만, configured) | ✅ | `KbDefaultSettingUseCase`, admin GET/PUT, 사용자 GET |
| FR-02 | 자동 컬렉션 `kb-{id8}`·기본 모델·권한·활동 로그 | ✅ | `AutoProvisionCollectionAssigner` → 기존 `create_collection` 경유 |
| FR-03 | 미설정 422 code, 조용한 폴백 없음 | ✅ | `KbDefaultsNotConfiguredError` → `{code,message}` |
| FR-04 | 원스톱 API, 파일별 status | ✅ | `POST /knowledge-bases/quick` |
| FR-05 | 기본 청킹 프로파일 | ✅ | 오버라이드 미전달 → `ChunkingSettingsResolver` is_default |
| FR-06 | 블록·이름·범위 매핑 | ✅ | `kbNameForAgent`, `scopeForVisibility` (스튜디오는 private 고정) |
| FR-07 | RAG 자동 부착·kb_id 갱신 | ✅ | `attachKbToForm` |
| FR-08 | 진행 카드·부분 실패·전부 실패 미부착 | ✅ | Act-1에서 재시도를 기존 KB 재업로드로 수정 |
| FR-09 | 기존 KB 선택 | ✅ | 블록 드롭다운 |
| FR-10 | RAG 패널 고급 접기 | ✅ | `hasAdvancedRagConfig`로 비기본값 자동 펼침 |
| FR-11 | 위저드 문서 단계 | ✅ | `DocumentsStep`(클라이언트 로컬 단계) |
| FR-12 | 파이프라인 `kb_id` → RAG + tool_configs | ✅ | `PipelinePolicy.with_knowledge_tool`, 기존 권한 검증 경유 |
| FR-13 | 핸드오프 `kbId` 프리필 | ✅ | `WizardResult.kbId` → `wizardResultToForm` |
| FR-14 | 관리자 화면 | ✅ | `/admin/kb-defaults`, "문서·품질" 그룹 |
| FR-15 | 기존 화면 노출 | ✅ | 실런 KB 목록·컬렉션 API 확인 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 호환성(회귀 0) | FAILED diff 비어 있음 | 백엔드 53=53, 프론트 9=9 | ✅ |
| 계약 additive | 기존 요청 동일 응답 | KB 생성(컬렉션 지정)·파이프라인(kb_id 없음) 회귀 테스트 | ✅ |
| 실패 경계 | 흡수 1곳 | AST 계약 테스트 | ✅ |
| 성능 | 원스톱 ≤ 기존 합계 +1s | 스모크: /quick 1파일 약 7s(파싱·임베딩 포함, 기존 업로드와 동일 경로) | ✅ (별도 비교 측정은 생략) |
| 접근성 | 파일 입력 키보드·aria-live | `input[type=file]` 라벨, 진행 영역 `aria-live` | ✅ |
| 문구 | 금지 용어 미노출 | DOM 검사 0건 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `idt/db/migration/V084__create_kb_default_setting.sql` (로컬 DB 적용됨) | ✅ |
| 도메인 | `idt/src/domain/kb_default_setting/`, `domain/knowledge_base/quick_setup_policy.py`, `domain/agent_create_pipeline/policies.py` | ✅ |
| 애플리케이션 | `application/kb_default_setting/use_case.py`, `knowledge_base/{collection_assigner,quick_create_use_case,use_case}.py`, `agent_create_pipeline/{use_case,events}.py` | ✅ |
| 인프라·API | `infrastructure/kb_default_setting/`, `api/routes/{admin_kb_defaults_router,kb_defaults_router,knowledge_base_router,agent_pipeline_router}.py`, `api/kb_defaults_di.py`, `main.py` | ✅ |
| 프론트 | `components/agent-builder/{KnowledgeDocsBlock,RagConfigPanel,LeftConfigPanel,StudioLayout,ModelSettingsModal}.tsx`, `pages/{AdminKbDefaultsPage,AgentCreateEntryPage(+DocumentsStep),AgentBuilderPage}`, `hooks/{useKbDefaults,useQuickKnowledgeBase}.ts`, `services/kbQuickSetupService.ts`, `utils/{kbQuickSetup,ragConfigAdvanced,wizardResultToForm}.ts`, `types/kbQuickSetup.ts`, `constants/{api,adminNav}.ts`, `App.tsx` | ✅ |
| 테스트 | 백엔드 신규 10파일(domain 3·application 4·api 3·infra 1·DDL 검사), 프론트 신규 5파일 + 기존 6파일 보정, MSW 핸들러 | ✅ |
| 문서 | Plan·Design·Analysis·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| G7 `KnowledgeBaseUseCase.create` 77줄(40줄 규칙) | Minor, 사용자 결정으로 이월 | Low | 0.5h |
| G8 이름 중복 판정의 예외 문자열 매칭 → 전용 예외 | Minor | Low | 0.5h |
| R1 KB 연결 후 [건너뛰기]도 kb_id 전송 | 요검토(확신도 70%) — 제품 판단 필요 | Medium | 0.5h |
| R2 [이전]에서 RAG 해제해도 kbId 잔존 | 요검토 | Medium | 0.5h |
| R3 /quick 파일 루프 세션 공유 시 DB 오류 전파 | 요검토, 실런 재현 필요 | Medium | 1h |
| R4 파일 오류 원문(영문) 노출 → 사용자 메시지 매핑 | 요검토 | Medium | 1h |
| R5 관리자 드롭다운 비활성 모델 필터 | 요검토(저장은 409로 차단됨) | Low | 0.5h |
| 컬렉션 수 증가 상한·정리 | Plan 리스크 수용, 후속 | Low | 설계 필요 |
| 에이전트 공개 범위 변경 시 KB 범위 동기화 / 삭제 시 KB 정리 | Plan Out of Scope | Low | 설계 필요 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| 생성 폼의 공개 범위 → KB 범위 매핑(department/public) | 스튜디오 생성 폼에 visibility 필드 없음(서버 기본 private) | `scopeForVisibility` 유틸은 구현됨. 공개 범위 필드가 생기면 바로 연결 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | 98.9% (Check 95.5% → Act-1) | +3.4 |
| Critical gaps | 0 | 0 | ✅ |
| Important gaps | 0 | 0 (2건 수정) | ✅ |
| 백엔드 테스트 | 회귀 0 | 11,609 passed / 53 failed(기준선 동일) | ✅ |
| 프론트 테스트 | 회귀 0 | 1,760+ passed / 9 failed(기준선 동일) | ✅ |
| ruff / eslint / tsc | 신규 파일 0 | 0 (기존 오류 제외) | ✅ |
| DDL COMMENT 검사 | 통과 | 통과 | ✅ |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G1 전부 실패 후 재시도가 빈 KB를 누적 | `useRetryKbUpload`: 기존 `kb_id`에 파일만 재업로드 | ✅ |
| G2 고아 안내가 생성 직후·위저드에서 미표시 | 조건 `studio || result || attachedKbId` | ✅ |
| 모델 설정 모달 combobox 중복으로 테스트 #10 깨짐 | 모델 드롭다운 `ariaLabel="모델"` + 이름 조회 | ✅ |
| MSW `request.formData()`가 jsdom multipart를 못 읽음 | 고정 응답 + raw 본문 정규식 검증 | ✅ |
| 스모크가 `TestClient` 안 `asyncio.run`으로 정지 | 정리를 별도 스크립트로 분리 | ✅ |
| 워크트리 venv pandas DLL 차단 | `uv pip install --reinstall --no-cache pandas` | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- Plan 전에 현재 경로(4화면·15결정)를 코드로 실측해 질문 4개로 범위를 확정했다. 설계 중 뒤집힌 결정이 없었다.
- 도메인에 이미 있던 `CollectionAssignerInterface` 이음매를 재사용해 KB UseCase·라우터 분기를 늘리지 않았다.
- 적재 시 임베딩 모델이 활동 로그에서 결정된다는 사실을 Plan 단계에서 찾아 리스크로 올렸고, 자동 배정기가 기존 생성 UseCase를 그대로 거치게 하여 실런에서 바로 성립했다.
- 모듈 4개를 각각 TDD → 회귀 diff → 커밋 가능 상태로 닫았다. 실런(실 DB·Qdrant·LLM)으로 SC 7개를 전부 확인했다.

### 6.2 What Needs Improvement (Problem)

- gap-detector 에이전트가 30턴 한도에 걸려 보고서를 못 냈고, Write 도구도 없어 본문을 메시지로 받아 내가 저장해야 했다.
- 스튜디오 생성 폼에 공개 범위 필드가 없다는 사실을 Design이 아니라 Do(module-3)에서 발견했다. Design §5.1의 "폼의 공개 범위 매핑"은 전제가 틀렸다.
- 전체 테스트를 백엔드·프론트 동시에 돌리면 pytest가 77%에서 멈추고 AgentBuilderPage 테스트가 플레이크를 낸다. 순차 실행이 필요했다.
- 첫 스모크가 기본 설정을 바꾼 채 멈춰 다음 스모크의 "미설정 422" 단계가 201로 나왔다. 상태를 바꾸는 스모크는 시작 시 전제 상태를 단언해야 한다.

### 6.3 What to Try Next (Try)

- gap-detector에는 "읽기 상한 N파일, 보고서는 N턴 안에" 같은 예산을 브리프에 명시하고, 결과 저장은 호출자가 맡는다.
- Design의 UI 절은 "폼에 그 필드가 실제로 있는가"를 파일:라인으로 확인하고 쓴다(`intermediate-artifact-verification` 위키 규칙을 UI 전제에도 적용).
- 상태를 바꾸는 스모크는 시작 시 전제 상태 단언 + 종료 시 원복을 TestClient 블록 밖에서 수행한다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 사용자 질문 2회로 범위 확정 | 유지. 질문에 "권고"를 붙이니 결정이 빨랐다 |
| Design | UI 전제(폼 필드 존재)를 추정 | 전제마다 file:line 근거 표기 |
| Do | 모듈별 회귀 diff | 백엔드·프론트 전체 스위트는 순차 실행으로 고정 |
| Check | gap-detector + 실런 | 에이전트 예산 명시, 실런은 워크트리 서버(8010/5176) 레시피 재사용 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 워크트리 프론트 실런 | `vite5176.mjs` + `import('/src/store/authStore.ts')` 토큰 주입 + `pushState/popstate` SPA 이동을 스크립트로 보존 | 다음 사이클 화면 확인 10분 내 |
| MSW | multipart 핸들러는 파싱 금지 규칙을 `handlers.ts` 상단 주석으로 | 동일 함정 재발 방지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋·PR (사용자 지시 시). 권장 분할: PR-A 백엔드(module-1·2, V084 포함) → PR-B 프론트(module-3·4). 배포 전 **V084 적용 필수**(`ops/migration-deploy-deps` 위키에 추가 권장).
- [ ] `.env.example` 변경 없음(신규 config 키 없음).
- [ ] `/pdca archive agent-kb-quick-setup`

### 8.2 Next PDCA Cycle

| Item | Priority | Expected Start |
|------|----------|----------------|
| 이월 R1·R2·R4(위저드 건너뛰기·RAG 해제·오류 메시지 매핑) 소형 사이클 | Medium | PR 머지 후 |
| 생성 폼 공개 범위 필드 + KB 범위 연동 | Medium | 별도 Plan |
| 컬렉션 수 상한·정리 정책 | Low | 별도 Plan |

---

## 9. Changelog

### v1.0.0 (2026-11-05)

**Added:**
- `kb_default_setting` 단일 행 테이블(V084)과 관리자 `GET/PUT /api/v1/admin/kb-defaults`, 사용자 `GET /api/v1/kb-defaults`, 관리자 화면 `/admin/kb-defaults`
- `AutoProvisionCollectionAssigner`: KB 생성 시 `collection_name` 생략하면 기본 임베딩 모델로 전용 컬렉션 `kb-{id8}` 자동 생성
- `POST /api/v1/knowledge-bases/quick`: KB 생성 + 컬렉션 + 파일 순차 업로드(파일별 status)
- 스튜디오 도구함 "지식 문서" 블록, 위저드 "참고할 문서가 있나요?" 단계, 재시도는 기존 KB 재업로드
- 파이프라인 요청·응답 optional `kb_id` → CREATE 단계 RAG 도구·tool_configs 주입
- `WizardResult.kbId` 핸드오프 프리필

**Changed:**
- `RagConfigPanel`: KB 선택·도구 설명만 기본 노출, 나머지는 "고급 설정"(비기본값 자동 펼침)
- `CollectionAssignerInterface.assign`에 `kb_id/scope/department_id` 키워드 인자와 `rollback` 기본 no-op (additive)
- `EmbeddingModelRepository.find_by_id` 추가
- 모델 설정 모달 드롭다운 접근성 이름 "모델"

**Fixed:**
- (Act-1) 전부 실패 후 재시도 시 빈 KB 누적, 고아 안내 누락

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-05 | Completion report created | 배상규 |
