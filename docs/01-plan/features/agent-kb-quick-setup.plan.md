# agent-kb-quick-setup Planning Document

> **Summary**: 에이전트 빌더(스튜디오·위저드) 안에서 문서 파일만 올리면 지식베이스·컬렉션·RAG 도구가 기본값으로 자동 구성되게 하여, 비개발자가 "문서로 답하는 에이전트"를 혼자 완성할 수 있게 한다.
>
> **Project**: sangplusbot (Agent Builder)
> **Version**: idt 0.1.0 / idt_front 0.0.0
> **Author**: 배상규
> **Date**: 2026-11-05
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트에 KB를 붙이려면 컬렉션 생성(임베딩 모델·벡터 크기·거리 함수) → KB 생성(컬렉션·청킹) → 문서 업로드 → 빌더에서 RAG 도구 설정(검색 모드·top_k·필터·토글)까지 4개 화면에서 약 15개 항목을 정해야 한다. 컬렉션이 없으면 KB 생성이 "관리자에게 요청하세요"로 멈춘다. 개발자가 아니면 완주하기 어렵다. |
| **Solution** | 관리자가 기본 임베딩 모델을 한 번 정해 두면, 빌더에서 파일을 올리는 것만으로 KB와 전용 컬렉션이 자동 생성되고 문서가 적재되며 RAG 도구가 기본 설정으로 부착된다. 기존 설정 항목은 "고급 설정"으로 접어 그대로 남긴다. 스튜디오 도구함과 대화형 위저드 양쪽에 같은 진입점을 둔다. |
| **Function/UX Effect** | 사용자가 정하는 것은 "어떤 파일을 올릴지"와 "에이전트 공개 범위" 두 가지로 줄어든다. KB 이름·범위는 에이전트를 따라가고, 진행 상태(KB 생성 → 업로드 n/m → 도구 부착)가 카드로 보인다. 기존 KB를 고르는 경로와 고급 설정은 유지된다. |
| **Core Value** | S1(KB 폐루프)의 성공 기준 "개발자 개입 없이 P2 혼자 완주"를 에이전트 생성 경로에서 실제로 성립시킨다. P2가 각 부서에서 에이전트를 직접 만드는 정도가 곧 확장 가능성이라는 시나리오 원칙을 코드로 뒷받침한다. |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | KB를 에이전트에 붙이는 데 4개 화면·약 15개 결정이 필요하고, 벡터 크기·거리 함수 같은 용어가 비개발자를 막는다. |
| **WHO** | P2 부서 담당자(비개발자)와 IT 운영자(반개발자). 관리자(P3)는 기본 임베딩 모델을 1회 설정한다. |
| **RISK** | KB마다 컬렉션 1개 전략으로 Qdrant 컬렉션 수가 KB 수만큼 늘어난다. 자동 생성 KB가 에이전트 저장 취소 후 고아로 남는다. 부분 업로드 실패를 성공으로 위장할 가능성. |
| **SUCCESS** | 신규 사용자가 스튜디오·위저드 각각에서 파일 업로드만으로 RAG 에이전트를 만들고 테스트 채팅에서 문서 근거 답변을 받는다. 기존 KB·컬렉션·RAG 설정 경로 회귀 0건. |
| **SCOPE** | M1 기본 임베딩 모델 설정·컬렉션 자동 배정 → M2 KB 원스톱 생성 API → M3 스튜디오 도구함 "지식 문서" 블록·RAG 패널 고급 접기 → M4 위저드 문서 단계 |

---

## 1. Overview

### 1.1 Purpose

에이전트 빌더 안에서 문서 파일을 올리는 행위 하나로 지식베이스·물리 컬렉션·RAG 도구 부착을 끝낸다. 비개발자는 컬렉션·벡터·청킹·검색 모드라는 용어를 보지 않고도 "문서로 답하는 에이전트"를 만든다.

### 1.2 Background

사용자 질문 "RAG의 KB를 쓰려면 세팅이 필요한데 처음 보는 사용자가 할 수 있을까"에서 출발했다. 코드 대조 결과는 다음과 같다.

| 구간 | 현재 상태 | 근거 |
|------|----------|------|
| 컬렉션 생성 | 영문 이름·임베딩 모델·벡터 크기·거리 함수·범위를 사용자가 직접 입력 | `idt_front/src/components/collection/CreateCollectionModal.tsx:26-32` |
| KB 생성 | 컬렉션이 없으면 "관리자에게 컬렉션 생성을 요청해주세요"로 중단 | `idt_front/src/components/knowledge-base/CreateKnowledgeBaseModal.tsx:183-186` |
| 컬렉션 배정 이음매 | `CollectionAssignerInterface`가 있으나 구현은 사용자 선택형 하나. `collection_name` 없으면 ValueError | `idt/src/application/knowledge_base/collection_assigner.py:26` |
| 기본 청킹 | 청킹 프로파일 `is_default` 전역 기본과 관리자 화면 존재 | `idt/db/migration/V041__create_chunking_profile.sql`, `/admin/chunking-profiles` |
| 기본 임베딩 모델 | 모델 목록만 있고 "기본" 표시 없음. 컬렉션 생성 시 모델명 또는 벡터 크기 중 하나 필수 | `idt/src/domain/embedding_model/entity.py`, `idt/src/api/routes/collection_router.py:246` |
| 적재 시 임베딩 결정 | 컬렉션 활동 로그의 CREATE 기록 `embedding_model`로 결정. 로그가 없으면 업로드 실패 | `idt/src/application/unified_upload/use_case.py:216-238` |
| 문서 업로드 | 동기 호출. 청크 수를 응답으로 반환 | `idt/src/api/routes/knowledge_base_router.py:557-587` |
| 빌더 RAG 설정 | KB·컬렉션·필터·검색 모드·top_k·토글 2종·도구 이름·설명이 모두 펼쳐져 있음 | `idt_front/src/components/agent-builder/RagConfigPanel.tsx` |
| KB 범위 → 에이전트 공개 범위 | KB scope가 에이전트 visibility를 clamp | `idt/src/application/agent_builder/create_agent_use_case.py:245`, `idt/src/domain/agent_builder/policies.py:79` |
| 위저드 | intent → tools → prompt → create → bind. RAG·KB를 전혀 다루지 않고 visibility는 private 고정 | `idt/src/application/agent_create_pipeline/use_case.py:316-331` |

사용자 확인 사항(2026-11-05):

- 범위: 빌더 안 원스톱. 스튜디오 도구함과 위저드 둘 다.
- 기본값 주인: 관리자 전역 설정. 신설 항목은 기본 임베딩 모델 하나. 청킹은 기존 프로파일 기본값 재사용, RAG 검색 기본값(top_k 5·하이브리드)은 코드 상수 유지.
- 컬렉션 전략: **KB마다 컬렉션 1개**. 에이전트별 KB를 따로 두는 설계 목표를 유지하기 위해 공유 컬렉션은 쓰지 않는다.
- 자동 생성 KB의 이름·범위는 에이전트를 따라간다. 에이전트를 저장하지 않아도 KB는 남고 `/knowledge-bases`에서 보인다.
- 대상 사용자: 비개발자(P2)와 반개발자(IT 운영자) 둘 다. 간단 모드가 기본, 고급 설정은 접어서 유지.

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` P2, S1 ("DB/Swagger 직접 조작 0회, P2 혼자 완주")
- 위키: `docs/wiki/frontend/screens/kb-screens.md`, `docs/wiki/frontend/screens/agent-screens.md`, `docs/wiki/backend/db/erd-kb.md`
- 위키 패턴: `docs/wiki/frontend/patterns/cross-route-draft-handoff.md` (G1~G5), `docs/wiki/frontend/patterns/common-card-components.md` (ProgressCard), `docs/wiki/backend/patterns/degradation-vs-failure-boundary.md`, `docs/wiki/conventions/additive-contract-extension.md`, `docs/wiki/conventions/config-single-source-at-consumption.md`
- 선례: `multimodal_setting` 단일 행 설정 (V065, `idt/src/application/multimodal/settings_use_case.py`), 청킹 프로파일 `is_default` (V041)

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 기본 임베딩 모델 설정 + 컬렉션 자동 배정 (백엔드)**
  - 단일 행 설정 테이블 `kb_default_setting`(기본 임베딩 모델 소프트 참조) + 관리자 GET/PUT API + 사용자 조회 API
  - `AutoProvisionCollectionAssigner`: KB 생성 시 `collection_name`이 없으면 KB 전용 컬렉션을 기본 임베딩 모델·Cosine으로 생성하고 KB scope와 같은 권한 행을 만든다
  - KB 생성 API에서 `collection_name` 생략 허용 (additive)
- [ ] **M2 KB 원스톱 생성 API (백엔드)**
  - 이름·범위·파일 목록을 받아 KB 생성 → 컬렉션 자동 생성 → 파일 순차 업로드를 한 요청으로 처리. 파일별 성공/실패를 응답에 담는다
  - 기본 청킹은 청킹 프로파일 `is_default`를 따른다
- [ ] **M3 스튜디오 도구함 "지식 문서" 블록 + RAG 패널 고급 접기 (프론트)**
  - 파일 드롭 → 자동 이름(`{에이전트명} 지식`)·범위(에이전트 공개 범위 매핑) → M2 호출 → 진행 카드 → 완료 시 RAG 도구 자동 추가 + `toolConfigs[RAG].kb_id` 설정
  - 같은 블록에서 "기존 지식베이스 선택" 가능
  - `RagConfigPanel`: KB 선택·도구 설명만 기본 노출, 컬렉션·필터·검색 모드·top_k·토글은 "고급 설정" 접기
- [ ] **M4 위저드 문서 단계 (프론트 + 파이프라인)**
  - 도구 확정 단계 뒤에 "참고할 문서가 있나요?"(건너뛰기 가능) 단계 추가. 파일 업로드 시 M2로 KB 생성
  - 파이프라인 요청에 `kb_id` 전달 → CREATE 단계가 RAG 도구를 `tool_ids`에 포함하고 `tool_configs[RAG] = {kb_id}`로 저장
  - "직접 만들기" 핸드오프 intent에 `kb_id`를 실어 스튜디오 폼을 프리필
- [ ] 관리자 화면 `/admin/kb-defaults` ("문서·품질" 그룹): 기본 임베딩 모델 선택 1개
- [ ] API 계약 동기화 (`idt_front/src/types`, `services`, `hooks`, `constants/api.ts`)

### 2.2 Out of Scope

- 에이전트 공개 범위를 나중에 바꿀 때 KB 범위를 따라 올리는 동기화 (KB 상세 화면의 기존 경로로 처리)
- 에이전트 삭제 시 자동 생성 KB·컬렉션 삭제 (고아 허용, 사용자가 KB 목록에서 지운다)
- 간단 모드에서 에이전트 하나에 KB 여러 개 부착 (고급 설정·기존 경로로 가능)
- RAG 검색 기본값(top_k·검색 모드·토글)의 관리자 설정
- 위저드가 LLM으로 "문서가 필요한 의도"를 판별해 단계를 자동 노출하는 기능 (항상 노출, 건너뛰기 가능)
- 업로드 비동기 잡 전환 (현재 동기 업로드 유지, 파일당 순차 호출)
- 기존 KB·컬렉션 화면의 용어·레이아웃 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 관리자는 기본 임베딩 모델을 1개 설정·조회할 수 있다. 설정은 단일 행이며 `embedding_model`의 활성 모델만 허용한다. 미설정이면 조회 응답에 `configured: false`를 돌려준다 | High | Pending |
| FR-02 | KB 생성 시 `collection_name`을 생략하면 KB 전용 컬렉션이 자동 생성된다. 이름은 `kb-{kb_id 앞 8자}` 형식, 임베딩 모델은 FR-01 설정, 거리 함수는 Cosine, 권한 범위는 KB scope·department를 따른다. 활동 로그에 CREATE가 기록되어 적재 시 임베딩 모델이 결정된다 | High | Pending |
| FR-03 | 기본 임베딩 모델이 미설정 상태에서 자동 배정을 요청하면 422와 "관리자가 기본 임베딩 모델을 설정해야 합니다" 메시지를 돌려준다. 조용한 폴백 금지 | High | Pending |
| FR-04 | 원스톱 생성 API는 이름·범위·부서·파일 1~N개를 받아 KB 생성 → 컬렉션 생성 → 파일 순차 업로드를 수행하고 `{kb_id, collection_name, documents: [{filename, status, chunk_count, error}]}`를 돌려준다. KB 생성 실패는 전체 실패(4xx/5xx), 파일 단위 실패는 `status: failed`로 응답에 남긴다 | High | Pending |
| FR-05 | 원스톱 생성의 청킹 설정은 청킹 프로파일 `is_default`를 적용한다. 기본 프로파일이 없으면 기존 업로드 기본값(child 500/50)으로 동작한다 | Medium | Pending |
| FR-06 | 스튜디오 도구함에 "지식 문서" 블록이 있다. 파일 드롭 시 KB 이름은 `{에이전트명} 지식`(이름이 비면 `새 에이전트 지식`), 범위는 폼의 공개 범위 매핑(private→PERSONAL, department→DEPARTMENT, public→PUBLIC)으로 FR-04를 호출한다 | High | Pending |
| FR-07 | FR-04 완료 시 RAG 도구(`internal:internal_document_search`)가 도구 목록에 자동 추가되고 `toolConfigs[RAG]`가 `DEFAULT_RAG_CONFIG + {kb_id}`로 설정된다. 이미 RAG 도구가 있으면 `kb_id`만 갱신한다 | High | Pending |
| FR-08 | 진행 상태(KB 생성 → 업로드 n/m → 도구 부착)를 `ProgressCard`로 표시한다. 파일 단위 실패는 카드에 파일명과 사유를 남기고, 성공한 파일이 1개 이상이면 도구 부착까지 진행한다. 전부 실패하면 도구를 부착하지 않는다 | High | Pending |
| FR-09 | 같은 블록에서 "기존 지식베이스 선택"으로 접근 가능한 KB를 고를 수 있고 FR-07과 같은 결과가 된다 | Medium | Pending |
| FR-10 | `RagConfigPanel`은 기본 상태에서 KB 선택과 도구 설명만 보이고, 컬렉션·메타데이터 필터·검색 모드·top_k·위키 우선·라우팅 검색·도구 이름은 "고급 설정" 아래 접힌다. 접힌 값은 그대로 저장·복원된다 | Medium | Pending |
| FR-11 | 위저드에 도구 확정 뒤 "참고할 문서" 단계가 있다. 건너뛰기 가능. 업로드 시 FR-04를 범위 PERSONAL로 호출하고 결과 `kb_id`를 이후 파이프라인 요청에 실어 보낸다 | High | Pending |
| FR-12 | 파이프라인 CREATE 단계는 `kb_id`가 있으면 RAG 도구를 `tool_ids`에 포함하고 `tool_configs[RAG]`에 `kb_id`를 저장한다. `kb_id`는 기존 `create_agent_use_case`의 존재·읽기 권한 검증을 그대로 거친다 | High | Pending |
| FR-13 | 위저드 "직접 만들기" 핸드오프 intent에 `kb_id`를 추가하고, 스튜디오는 G1~G5 계약대로 소비해 FR-07 상태로 프리필한다 | Medium | Pending |
| FR-14 | 관리자 메뉴 "문서·품질" 그룹에 "지식베이스 기본값" 항목을 추가한다. 임베딩 모델 드롭다운 1개와 저장 버튼. 미설정 경고 문구 표시 | Medium | Pending |
| FR-15 | 자동 생성된 KB·컬렉션은 기존 `/knowledge-bases`·`/collections` 화면에 그대로 나타나며 기존 편집·삭제 경로가 동작한다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 호환성 | 기존 KB 생성(컬렉션 지정)·컬렉션 생성·RAG 설정 저장 경로 회귀 0건 | 백엔드·프론트 회귀는 정렬된 `FAILED` 목록 diff (`false-green-quality-gates`) |
| 계약 | 모든 API 변경은 additive (optional 필드·신규 엔드포인트) | 기존 요청 본문으로 기존 응답 동일 단언 테스트 |
| 실패 경계 | KB 생성 실패는 전파, 파일 단위 실패는 degraded | FR-04 응답 계약 테스트 + AST 계약 테스트(흡수 지점 1곳) |
| 성능 | 파일 1개(10MB PDF) 원스톱 생성이 기존 KB 생성 + 업로드 합계 대비 +1s 이내 | 로컬 실측 1회 (E2E 이월 체크리스트 등재) |
| 접근성 | 파일 드롭 영역은 키보드 선택(input file) 가능, 진행 카드는 `aria-live` | RTL 테스트 |
| 문구 | 간단 모드 화면에 "컬렉션·벡터·거리 함수·청킹·BM25·RRF·top_k" 용어 미노출 | 컴포넌트 테스트에서 텍스트 부재 단언 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 스튜디오에서 PDF 1개 드롭 → 저장 → 테스트 채팅에서 문서 근거 답변 수신 (실런 스모크, 화면 확인)
- [ ] SC-2 위저드에서 문서 단계에 PDF 1개 업로드 → 생성 완료 → 생성된 에이전트 상세에 RAG 도구와 KB가 연결되어 있음
- [ ] SC-3 기본 임베딩 모델 미설정 상태에서 FR-03 메시지가 화면에 그대로 노출됨
- [ ] SC-4 파일 2개 중 1개 실패(암호 PDF) 시 카드에 실패 파일명이 남고 성공 파일로 도구 부착이 완료됨
- [ ] SC-5 자동 생성 KB가 `/knowledge-bases` 목록에 `{에이전트명} 지식`으로 보이고 범위 배지가 에이전트 공개 범위와 일치
- [ ] SC-6 간단 모드 화면 텍스트에 금지 용어 7종이 없음
- [ ] SC-7 백엔드·프론트 회귀 `FAILED` 목록 diff가 비어 있음
- [ ] 모든 FR에 테스트 선행(TDD), 신규 DDL에 테이블·전 컬럼 COMMENT

### 4.2 Quality Criteria

- [ ] use-case 테스트 전수, domain 테스트 mock 없음 (`docs/rules/testing.md`)
- [ ] `tsc -b`·lint 0 에러
- [ ] 신규 config 키 없음 (기본 임베딩 모델은 DB 설정 단일 출처)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| KB마다 컬렉션 1개라 Qdrant 컬렉션이 KB 수만큼 증가 (콜드스타트·관리 부담) | Medium | High | 사용자 결정 사항으로 수용. 이름 접두 `kb-`로 식별, 컬렉션 화면에 "KB 전용" 배지. 상한·정리는 후속 사이클로 명시 이월 |
| 에이전트를 저장하지 않아 고아 KB·컬렉션이 남음 | Low | Medium | 수용(사용자 결정). KB 목록에서 보이므로 삭제 가능. 생성 직후 카드에 "저장하지 않아도 지식베이스는 남습니다" 안내 |
| 부분 업로드 실패를 성공으로 위장 | High | Medium | FR-04 파일별 status 계약 + FR-08 전부 실패 시 도구 미부착. degraded 흡수 지점은 업로드 루프 1곳으로 고정(AST 테스트) |
| 적재 시 임베딩 모델을 활동 로그에서 읽는 구조라 자동 컬렉션에 로그가 없으면 업로드 실패 | High | Low | 자동 배정은 기존 `CollectionManagementUseCase.create_collection`을 그대로 호출해 로그를 남긴다. 통합 테스트로 "자동 컬렉션 → 업로드 성공" 고정 |
| KB scope가 에이전트 visibility를 clamp하여 사용자가 의도한 공개 범위와 어긋남 | Medium | Medium | FR-06 매핑으로 동일하게 맞춤. 이후 범위 변경 시 clamp 알림은 기존 경로 유지 |
| 위저드 파이프라인이 `tool_configs`를 받지 않아 `kb_id` 전달 경로가 없음 | Medium | High | 파이프라인 요청·CREATE 단계에 optional `kb_id` 추가(additive). 기존 `tool_configs: dict[str, RagToolConfigRequest]` 계약 재사용 |
| 동기 업로드라 대용량·다수 파일 시 요청 시간 초과 | Medium | Medium | 파일당 1요청(프론트 순차 호출) 또는 서버 순차 처리 중 Design에서 택일. 파일 수·용량 상한을 UI에서 안내 |
| 기본 임베딩 모델을 바꾸면 이전 자동 컬렉션과 모델이 달라짐 | Low | Low | 컬렉션은 생성 시점 모델을 로그로 고정하므로 기존 컬렉션 영향 없음. 관리자 화면에 "변경은 이후 생성분에만 적용" 문구 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `kb_default_setting` | DB Model (신규 V084) | 단일 행. `default_embedding_model_id` 소프트 참조(`embedding_model.id`). COMMENT 필수 |
| `POST /api/v1/knowledge-bases` | API | `collection_name` optional로 완화 (additive) |
| `POST /api/v1/knowledge-bases/quick` | API (신규) | 이름·범위·파일 다중 → KB+컬렉션+업로드 |
| `GET/PUT /api/v1/admin/kb-defaults`, `GET /api/v1/kb-defaults` | API (신규) | 기본 임베딩 모델 설정 |
| `CollectionAssignerInterface` 구현 | Application | `AutoProvisionCollectionAssigner` 추가. 기존 `UserSelectedCollectionAssigner`는 `collection_name` 있을 때 그대로 |
| `AgentPipelineRequest` / `CreateAgentPipelineUseCase._run_create` | Schema / Application | optional `kb_id` 추가, RAG 도구·tool_configs 주입 |
| `AgentCreateIntent` | Front type | optional `kbId` 추가 |
| `RagConfigPanel`, `LeftConfigPanel` | Front component | 고급 접기, "지식 문서" 블록 |
| `AgentCreateEntryPage` + `WizardProgress` | Front page | 문서 단계 추가 |
| `adminNav.ts` | Front const | "지식베이스 기본값" 항목 |
| `constants/api.ts`, `types/`, `services/`, `hooks/` | Front | 신규 엔드포인트 상수·타입·훅 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| KB 생성 API | CREATE | `CreateKnowledgeBaseModal` → `useKnowledgeBases` → `knowledge_base_router.create` | None (컬렉션 지정 경로 유지) |
| `UserSelectedCollectionAssigner` | READ | `KnowledgeBaseUseCase.create` (`collection_assigner.py`) | Needs verification — `collection_name` None 분기를 자동 배정기로 위임 |
| `CollectionManagementUseCase.create_collection` | CREATE | `collection_router.create_collection`, 자동 배정기(신규) | None (호출 추가) |
| 컬렉션 활동 로그 CREATE | READ | `unified_upload/use_case.py:_resolve_embedding_model` | Needs verification — 자동 컬렉션도 로그를 남겨야 업로드 성공 |
| `create_agent_use_case` kb_id 검증·clamp | CREATE | 스튜디오 저장, 파이프라인 CREATE(신규 경유) | None (기존 검증 재사용) |
| `update_agent_use_case` visibility clamp | UPDATE | 스튜디오 수정 저장 | None |
| `AgentPipelineRequest` | CREATE | `AgentCreateEntryPage` → `useAgentPipelineStream` → `agent_pipeline_router` | None (optional 필드) |
| `agentDraftStore.pendingIntent` | READ | `AgentBuilderPage` consume (G1~G5) | Needs verification — `kbId` 소비 시 KB 쿼리 settled 후 적용 |
| `RagConfigPanel` 테스트 | — | `RagConfigPanel.test.tsx`, `RagConfigModal.test.tsx`, `LeftConfigPanel.test.tsx` | Needs verification — 접힘 상태에서 기존 단언이 요소를 못 찾을 수 있음 |
| `adminNav` 테스트 | — | `layout-owned-nav-tabs` 규칙(개수 하드코딩 금지) | None |
| 청킹 프로파일 `is_default` | READ | `KnowledgeBaseUploadUseCase._resolve_chunking` | None (기존 해석 재사용) |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 요청으로 동일 응답 확인
- [ ] 권한: 자동 컬렉션 권한 행이 KB scope와 일치, 타 사용자 비노출
- [ ] optional 필드 추가로 기존 쿼리·뮤테이션 파손 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems, complex architectures | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 기본 임베딩 모델 저장 | DB 단일 행 / `.env` / `embedding_model.is_default` 컬럼 | DB 단일 행 (`multimodal_setting` 선례) | 관리자 화면에서 바꿀 수 있어야 하고, 모델 테이블에 플래그를 넣으면 유일성 보장을 모델 CRUD마다 신경 써야 함 |
| 컬렉션 자동 배정 위치 | `CollectionAssignerInterface` 신규 구현 / KB UseCase 분기 / 라우터 | 신규 구현 (`AutoProvisionCollectionAssigner`) | 이음매가 이미 도메인에 있음. UseCase·라우터 무변경 |
| 원스톱 오케스트레이션 | 서버 단일 엔드포인트 / 프론트가 기존 API 2종 순차 호출 | **Design에서 택일** (권고: 서버 단일 엔드포인트 + 파일별 status) | 위저드·스튜디오 두 호출자가 같은 흐름을 쓰므로 서버에 두면 중복이 없음. 단, 요청 시간·멀티파트 다중 파일 처리는 Design에서 검증 |
| 위저드 `kb_id` 전달 | 요청 optional 필드 / tools_confirmed 목록에 RAG 포함 후 별도 PATCH | 요청 optional 필드 | 생성 1회로 끝나야 함. PATCH 분리는 실패 시 KB 없는 RAG 도구가 남음 |
| 고급 접기 | 새 간단 패널 컴포넌트 / 기존 패널에 `CollapsibleSection` | 기존 패널 + 접기 | 저장·복원 로직 무변경. 테스트는 접힘 열기만 추가 |
| 진행 표시 | 신규 / `common/ProgressCard` | `ProgressCard` | 위키 규칙(신규 구현 = 중복) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

domain/knowledge_base/        KB 정책(이름·범위) 기존 + 자동 컬렉션 이름 규칙(VO)
domain/kb_default_setting/    단일 행 설정 엔티티·검증
application/knowledge_base/   AutoProvisionCollectionAssigner, QuickCreateKnowledgeBaseUseCase
application/kb_default_setting/  Settings UseCase (GET/PUT)
application/agent_create_pipeline/ _run_create kb_id → RAG 도구 주입
infrastructure/db/            kb_default_setting 리포지토리 (V084)
api/routes/                   admin_kb_defaults_router, knowledge_base_router(/quick)
idt_front/                    agent-builder/KnowledgeDocsBlock, RagConfigPanel 접기,
                              AgentCreateEntryPage/components/DocumentsStep, AdminKbDefaultsPage
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (루트·idt·idt_front 3종)
- [x] DDL COMMENT 검사 (`tests/db/test_migration_ddl_comments.py`)
- [x] ESLint / Prettier / TypeScript 설정
- [x] 위키 패턴 문서 (§1.3)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 자동 컬렉션 이름 | 없음 | `kb-{kb_id[:8]}` 고정, 충돌 시 생성 실패 → KB 생성 롤백 | High |
| 자동 KB 이름 | 없음 | `{에이전트명} 지식` (KB 이름 정책 최대 길이 내 절단), 중복 시 ` (2)` 접미 | High |
| 금지 용어 목록 | 없음 | 컬렉션·벡터·거리 함수·청킹·BM25·RRF·top_k — 간단 모드 텍스트 테스트 상수 | Medium |
| 파일별 status 값 | 없음 | `uploaded` / `failed` 문자열 상수 (프론트 타입 동기) | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | 기본 임베딩 모델은 DB 설정이 단일 출처 | — | ☐ |

### 8.4 Pipeline Integration

해당 없음 (PDCA 단독).

---

## 9. Next Steps

1. [ ] `/pdca design agent-kb-quick-setup` — 원스톱 오케스트레이션 위치(서버/프론트) 택일, V084 DDL, `/quick` 응답 스키마, 위저드 단계 상태 전이 확정
2. [ ] Design 승인 후 M1 → M2 → M3 → M4 순서로 worktree에서 구현 (M1·M2는 백엔드 단독 PR 가능)
3. [ ] E2E 이월 체크리스트에 SC-1·SC-2·SC-4 등재

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-05 | Initial draft — 사용자 확인 5건 반영 | 배상규 |
