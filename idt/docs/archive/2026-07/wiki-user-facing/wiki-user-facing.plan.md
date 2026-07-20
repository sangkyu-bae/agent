# wiki-user-facing Planning Document

> **Summary**: LLM Wiki의 **사용자 노출** — ① 에이전트 소유자의 위키 직접 작성(`source_type=human` 예약석 활용, 셀프서비스), ② `path` 컬럼(V051) 기반 지식 트리 브라우저, ③ 채팅 답변의 "근거 위키 보기" 링크(투명성). 에이전트를 블랙박스에서 "구성이 보이는 폴더"로 바꾸는 첫 단계
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 풀스택)
> **Author**: 배상규
> **Date**: 2026-07-18
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 위키는 관리자 전용 화면(/admin/wiki)에만 노출되고, 생성 경로는 distill(문서 정제)뿐이다. 에이전트를 만든 사용자가 "우리 에이전트가 꼭 알아야 할 것"을 직접 써넣을 방법이 없고, 일반 사용자는 에이전트가 무엇을 알고 어디서 근거를 가져왔는지 볼 수 없다 — 에이전트가 블랙박스다. |
| **Solution** | ① 소유자 직접 작성 API(`POST /wiki`, `source_type=human` — enum 예약석 활용)로 자기 에이전트 지식 셀프서비스, ② `wiki_article`에 `path` 컬럼(V051)을 추가해 "여신/한도/…" 가상 폴더 트리로 지식 브라우저 제공, ③ 채팅 답변의 위키 유래 출처(`source="wiki"` 기존 마킹)를 `SourceCitation`에서 배지+링크로 노출해 문서 뷰로 연결한다. 저장은 DB(거버넌스 유지), 경험은 파일 위키(계층·인덱스·문서성). |
| **Function/UX Effect** | 에이전트 소유자: 설정에서 지식 문서를 직접 작성·분류·관리. 일반 사용자: 에이전트의 지식 트리를 문서처럼 탐색하고, 답변 아래 "📖 근거" 배지를 눌러 출처 위키를 확인. "AI가 어디서 이 말을 하는지"가 클릭 한 번으로 검증 가능해진다. |
| **Core Value** | 블랙박스 해소 = 엔터프라이즈 도입 신뢰의 전제. 비전 원칙 6(투명성)의 갭을 메우고, 위키 가이드 §10의 "human 신규 작성 API 없음" 한계를 해소하며, 성장형 에이전트의 지식 축에 **사람이 직접 기여하는 세 번째 생성 경로**(distill·환류에 이어)를 연다. |

---

## 1. Overview

### 1.1 Purpose

LLM Wiki를 관리자 전용 자산에서 사용자 대면 기능으로 확장한다:
소유자 직접 작성(셀프서비스) + path 트리 탐색(지식 브라우저) + 답변 근거 링크(투명성).

### 1.2 Background (현재 구조 분석 — 2026-07-18 확인)

| 항목 | 현재 상태 | 근거 코드 |
|------|-----------|----------|
| 위키 조회 API | `GET /wiki`, `GET /wiki/{id}` — **이미 일반 로그인 사용자 접근 가능** (`get_current_user`) | `src/api/routes/wiki_router.py:71-90` |
| 위키 쓰기 API | distill·approve·reject·deprecate·restore·edit 전부 **admin 전용** | `wiki_router.py:53-147` |
| human 작성 예약석 | `WikiSourceType.HUMAN`("사람 작성") enum 존재 — **생성 API만 부재** (가이드 §10 한계) | `src/domain/wiki/entity.py` |
| 분류 체계 | **없음** — 위키는 agent_id 스코프의 flat 리스트. path/category 컬럼 부재 | `src/infrastructure/wiki/models.py` |
| 답변의 위키 마킹 | 위키 유래 검색 결과에 `source="wiki"` + `metadata.title/source_type/status` 이미 포함 | `wiki_first_search_use_case.py`, 가이드 §6-3 |
| 프론트 출처 표시 | `SourceCitation.tsx` / `MessageBubble.tsx` — 출처 렌더링 컴포넌트 존재(위키 구분 없음) | `idt_front/src/components/chat/` |
| 에이전트 소유자 판정 | `agent_owner_id` 기반 접근 정책 선례 (`AgentAccessPolicy`) — 소유자 검증 재사용 가능 | `src/domain/agent_builder/policies.py:27-56` |
| 위키 관리 UI | `/admin/wiki` (WikiPage) — 관리자 전용. 사용자용 열람 화면 없음 | `idt_front/src/pages/WikiPage/` |
| 마이그레이션 | 최신 V049, V050은 agent-memory 예정 → 본 기능은 **V051** | `db/migration/` |

### 1.3 Related Documents

- 방향 근거: `docs/architecture/growing-agent-vision.md` (원칙 6 투명성), `docs/architecture/llm-wiki-vs-growing-agent-vision.md` (§5-1 스코프 모델, §2-2 한계)
- 위키 현행 가이드: `docs/guides/llm-wiki.md`
- 규칙: `idt/CLAUDE.md`, `docs/rules/db-session.md`, 루트 `CLAUDE.md` §4-1(API 계약 동기화)

### 1.4 사용자 확정 사항 (대화 2026-07-18)

| 질문 | 결정 |
|------|------|
| 직접 작성 필요성 | **필요** — distill 대기가 아니라 소유자가 핵심 지식을 직접 써넣을 수 있어야 함 (`HUMAN` 예약석 활용) |
| 거버넌스 기준 | "누가 쓰느냐"가 아니라 **"어디까지 퍼지느냐"** — agent 스코프(자기 에이전트)는 셀프서비스, org 공유는 승인 게이트(후속) |
| 노출 방향 | 에이전트를 "구성이 보이는 폴더"로 — 블랙박스 해소는 신뢰 기능 |
| 저장/경험 분리 | 저장은 DB 유지(승인·동시성·스코프), **경험만 파일 위키식**(트리·문서성) |

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**
- [ ] **V051** 마이그레이션: `wiki_article`에 `path` VARCHAR(255) NULL 컬럼 + 인덱스 (예: `여신/한도/동일인여신한도`). 기존 행은 NULL 허용(미분류), distill 신규 생성분은 컬렉션명 기반 기본 path 부여
- [ ] 소유자 직접 작성 API: `POST /api/v1/wiki` — `source_type=human`, 본인 소유 에이전트(`agent_owner_id` 검증) 대상만. **생성 시 상태 정책(즉시 approved vs draft)은 Design에서 확정** — 선호안: agent 스코프 셀프서비스(즉시 approved + reviewer_id=본인), 보수안: draft 후 소유자 자가 승인
- [ ] 소유자 편집/폐기 확장: 기존 admin 전용 `PUT /wiki/{id}`·`PATCH deprecate`를 **소유자에게도 허용** (source_type=human + 본인 에이전트 것만 — 범위는 Design 확정). 기존 admin 권한은 무변경 유지
- [ ] 트리 조회 API: `GET /api/v1/wiki/tree?agent_id=...` — path 프리픽스 그룹핑 트리(분류별 제목 목록). 열람 권한은 현행 유지(로그인 사용자) — 강화 여부 Design 확정
- [ ] `WikiPolicy` 확장: human 생성 불변식(source_refs 처리 — **사람 작성은 출처가 본인**이므로 `human:{user_id}` 형식 등 출처 표기 방식 Design 확정), 소유자 권한 전이 규칙
- [ ] pytest 선행 작성 (TDD: 생성 정책·소유자 검증·타 소유자 403·트리 그룹핑·기존 admin 경로 회귀)

**프론트엔드 (idt_front/)**
- [ ] 답변 근거 배지: `SourceCitation`에서 `source==="wiki"` 결과를 "📖 근거: {title}" 배지로 구분 표시, 클릭 시 위키 문서 뷰 이동 — **백엔드 무변경**
- [ ] 지식 브라우저: 에이전트별 위키 트리(path 폴더 구조) + 문서 뷰(제목·본문·출처·상태). 진입점은 에이전트 상세/스토어의 "지식" 탭 — 위치는 Design 확정
- [ ] 소유자 작성 UI: 지식 브라우저 내 "문서 작성/수정" (소유자에게만 노출) — 제목·본문·path 입력
- [ ] API 계약 동기화: `constants/api.ts`, `types/wiki.ts` 확장, `services/wikiService.ts` + 훅 — Vitest+MSW 테스트 선행 (`--pool=threads`, MSW 파일별 3종 훅)

### 2.2 Out of Scope

- **org 스코프 확장** — 비교 문서 §5-1의 스코프 모델 결정(위키 scope 컬럼 vs agent_memory 담당) 대기. 본 기능은 agent 스코프 내에서만
- 비소유자의 수정 제안 워크플로 (제안 → pending → 승인) — 후속 후보
- 에이전트 워크스페이스 종합 뷰 (프롬프트/도구까지 폴더식 열람 + 프롬프트 2단 공개 정책) — 후속 feature `agent-workspace-view` 후보. 본 기능은 지식(위키) 탭까지만
- distill 중복 검사 수정 — 별도 fix feature (`fix-wiki-distill-dedup` 후보)
- 환류 생성(`CONVERSATION`)·confidence 갱신·ES BM25 — 비전 로드맵 Phase 2·4 잔여
- 기존 `/admin/wiki` 관리 화면 변경 (무변경 기준선)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 에이전트 소유자는 자기 에이전트의 위키 문서를 직접 작성할 수 있다 (`source_type=human`, path 지정 가능) | High | Pending |
| FR-02 | 타인 소유 에이전트에 작성 시도 시 403 — `agent_owner_id` 검증 | High | Pending |
| FR-03 | 소유자 작성 문서의 노출 상태는 Design 확정 정책을 따르며, 어느 안에서도 감사 필드(editor_id/reviewer_id)가 기록된다 | High | Pending |
| FR-04 | 소유자는 자신이 소유한 에이전트의 human 문서를 편집·폐기할 수 있다. admin의 기존 권한은 회귀 없다 | High | Pending |
| FR-05 | 트리 API가 path 기반 폴더 구조(분류 → 문서 제목 목록)를 반환한다. path NULL 문서는 "미분류"로 노출 | High | Pending |
| FR-06 | 지식 브라우저에서 트리 탐색 → 문서 뷰(제목/본문/출처/상태/갱신일)가 동작한다 | High | Pending |
| FR-07 | 채팅 답변의 위키 유래 출처가 일반 출처와 구분된 배지로 표시되고, 클릭 시 해당 위키 문서 뷰로 이동한다 | High | Pending |
| FR-08 | 위키 문서 작성/수정 UI는 소유자에게만 노출된다 (비소유자는 읽기 전용) | Medium | Pending |
| FR-09 | human 문서 생성 시에도 위키 불변식(제목/본문 길이)이 검증되고, 출처 필드는 Design 확정 형식으로 기록된다 | High | Pending |
| FR-10 | distill 신규 생성 문서에 컬렉션명 기반 기본 path가 부여된다 (기존 행 마이그레이션은 하지 않음 — NULL 유지) | Medium | Pending |
| FR-11 | 프론트 타입/서비스/훅/엔드포인트 상수가 백엔드 계약과 동기화된다 (루트 CLAUDE.md §4-1) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | 소유자 권한 규칙은 domain(WikiPolicy 확장), 라우터는 위임만. domain→infra 참조 금지, Repository 내 commit 금지, 단일 세션 | `/verify-architecture` |
| 호환성 | 기존 admin API·/admin/wiki 화면·wiki-first 검색 회귀 0. `path`는 NULL 허용 추가 컬럼 — 기존 행 무변경 | pytest (Windows 격리 실행 기준) |
| 거버넌스 | 검색 노출 조건(`is_searchable`: approved+미만료)은 어떤 생성 경로에서도 불변 — human 문서도 동일 게이트 | 정책 단위 테스트 |
| 성능 | 트리 API는 path·title만 조회(본문 제외), agent_id+path 인덱스 활용 | 쿼리 리뷰 |
| TDD | 신규 모듈 테스트 선행 작성 (Red→Green) | `/verify-tdd` |
| 로깅 | 작성/편집/폐기를 request_id 포함 구조화 로그로 기록 (print 금지) | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR 전체 구현: 소유자가 문서 작성 → 지식 트리에 표시 → (approved 시) 위키 우선 검색에 반영 → 채팅 답변 근거 배지 → 클릭해 문서 확인
- [ ] 검색 반영 실측: 직접 작성 문서가 `use_wiki_first` 에이전트의 답변 출처로 등장 (LangSmith/응답 metadata 확인)
- [ ] pytest 선행 작성(Red→Green) + 기존 wiki 테스트 7개 영역 회귀 0
- [ ] Vitest(MSW 파일별 3종 훅, `--pool=threads`) 통과
- [ ] Gap 분석(Check) ≥ 90%

### 4.2 Quality Criteria

- [ ] 레이어 의존성 규칙 위반 0 (`/verify-architecture`)
- [ ] 신규 함수 40줄 이하, if 중첩 2단계 이하
- [ ] 사전 실패 테스트(백엔드 api 28건·infra 30건, 프론트 8건)는 기존 이슈 — 신규 회귀로 오인 금지
- [ ] E2E(실서버: 작성→검색 반영→근거 링크) 수동 검증 — V051 적용 선행, 공통 이월 체크리스트 등재

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 소유자 즉시 approved 정책 시 저품질/오류 지식이 게이트 없이 검색 노출 | Medium | Medium | Design에서 상태 정책 확정(보수안: draft+자가승인 절차 유지). 어느 안에서도 agent 스코프라 피해 반경은 본인 에이전트 한정 + deprecate 즉시 회수 가능 |
| human 문서의 source_refs 불변식 충돌 (출처 청크가 없음) | High | High | 출처 불변식을 깨지 않고 `human:{user_id}` 등 출처 표기 형식으로 충족 — WikiPolicy 분기 방식 Design 확정. **불변식 자체 완화는 금지** |
| 열람 권한이 현행 "전체 로그인 사용자"라 민감 지식 노출 우려 | Medium | Medium | 현행 조회 API가 이미 동일 정책(신규 확대 아님)임을 명시. 에이전트 접근권 연동 강화는 Design에서 검토, org 스코프 결정과 함께 재론 |
| path 자유 입력으로 트리 난립 (오타 분류, 깊이 폭주) | Low | High | path 깊이·세그먼트 길이 제한(Policy), 작성 UI에서 기존 path 자동완성. 정리 도구는 후속 |
| admin 전용 API의 소유자 확장이 기존 권한 회귀 유발 | High | Low | 기존 admin 경로 무변경 + 소유자 분기 추가 방식(독립 opt-in 선호 선례). admin 회귀 테스트 명시 |
| SourceCitation 변경이 기존 출처 렌더링 회귀 | Low | Medium | `source==="wiki"` 분기 추가만 — 기존 경로 스냅샷 테스트 유지 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

기존 프로젝트 편입 — Thin DDD(Domain→Application→Infrastructure) 현행 유지.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 직접 작성의 구현 위치 | ① 신규 테이블 ② 기존 `wiki_article` + `source_type=human` | ② 기존 활용 | `HUMAN` enum이 예약돼 있고 승인·검색·UI 전부 재사용 — 신규 테이블은 이원화 비용만 발생 |
| 분류 체계 | ① 별도 category 테이블 ② path 문자열 컬럼 | ② path 컬럼 | 파일 위키의 경로 은유 그대로, 조인 없이 프리픽스 그룹핑. 깊이 제한은 Policy로 |
| 거버넌스 기준 | ① 생성 주체별 게이트 ② 전파 범위별 게이트 | ② 전파 범위 | 대화 확정 — agent 스코프(자기 에이전트)는 셀프서비스, org 전파만 승인 필수(후속) |
| 소유자 판정 | ① 위키 도메인에 자체 구현 ② agent_builder의 `agent_owner_id` 정책 재사용 | ② 재사용 | `AgentAccessPolicy` 선례와 판정 일관성 — 이중 구현 방지 |
| 근거 링크 구현 | ① 백엔드 응답 확장 ② 기존 `source="wiki"` 마킹 활용 | ② 기존 마킹 | 백엔드 무변경 — metadata에 title 등 필요 정보 이미 존재 |
| 기존 행 path 처리 | ① 일괄 백필 ② NULL 유지("미분류") | ② NULL 유지 | 임의 분류 강제보다 소유자/관리자가 점진 정리 — 데이터 임의 변경 회피 |

### 6.3 Clean Architecture Approach

domain: `WikiPolicy`에 human 생성 규칙·소유자 권한 전이·path 제약 추가 (엔티티 필드 `path` 추가).
application: `CreateHumanArticleUseCase`(또는 기존 review/distill 유스케이스와 대칭 구조), `WikiTreeQueryUseCase`.
infrastructure: 모델 `path` 컬럼, repository 트리 그룹핑 쿼리.
interfaces: `wiki_router`에 POST·tree 엔드포인트 추가(기존 admin 경로 무변경).
프론트: 지식 브라우저 컴포넌트 + SourceCitation 분기 + 소유자 작성 폼.

---

## 7. Convention Prerequisites

- [x] `idt/CLAUDE.md` + `docs/rules/testing.md` 준수 (TDD 필수)
- [x] 로깅: LoggerInterface + request_id (print 금지)
- [x] DB: V051 마이그레이션(NULL 허용 컬럼 추가 — FK 없음), Repository 내 commit 금지, 단일 세션
- [x] 권한: 기존 admin 경로 무변경 + 소유자 분기 추가 (독립 opt-in 선례)
- [x] 프론트: API 상수 `constants/api.ts` 집중, MSW 파일별 3종 훅, Vitest `--pool=threads`

신규 환경변수 없음. path 제약값(깊이·길이)은 config/Policy 상수로 (하드코딩 금지).

---

## 8. Next Steps

1. [ ] `/pdca design wiki-user-facing` — 확정 대상: ① human 문서 생성 상태 정책(즉시 approved vs draft+자가승인) ② source_refs 출처 표기 형식 ③ 소유자 편집 허용 범위 ④ 열람 권한(현행 유지 vs 에이전트 접근권 연동) ⑤ 지식 브라우저 진입점(에이전트 상세 탭 위치) ⑥ 트리 API 응답 스키마
2. [ ] 구현 (TDD: WikiPolicy 확장 → V051/모델 → 생성·트리 유스케이스 → 라우터 → 프론트 타입/서비스/훅 → 근거 배지 → 지식 브라우저)
3. [ ] `/pdca analyze wiki-user-facing`
4. [ ] 후속 분리: `agent-workspace-view`(프롬프트/도구 종합 열람 + 2단 공개), `fix-wiki-distill-dedup`, org 스코프 결정(비교 문서 §5-1)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-18 | Initial draft — HUMAN 예약석 활용 직접 작성·path 트리·근거 링크 3축 확정, 전파 범위 기준 거버넌스(대화 반영), org 스코프·워크스페이스 뷰는 후속 분리 | 배상규 |
