# agent-opener Completion Report

> **Feature**: agent-opener — 에이전트별 대화 시작 예시 질문(오프너) 등록·노출
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트엔드)
> **Period**: 2026-10-24 ~ 2026-10-26
> **Author**: 배상규
> **Final Match Rate**: **100%** (Check 96.1% → Act-1 후 100%)
> **Status**: Completed (미커밋)

---

## Executive Summary

### 1.1 Project Overview

빌더 우측 패널에 placeholder로만 있던 **오프너 탭**을 실기능으로 만들고, 에이전트 소유자가 등록한 예시 질문을 채팅 빈 상태에서 카드로 보여줘 클릭 한 번에 대화를 시작하게 했다. 백엔드는 별도 테이블 `agent_opener`와 포트·리포지토리를 신설하고 create/update/get/my-list/fork API에 additive로 `openers`를 더했다. 프론트는 폼 staged + 상단 저장 통합, 채팅 빈 상태는 `SuggestionCards`의 optional prop 하나로 분기한다.

### 1.2 Results Summary

| 항목 | 결과 |
|---|---|
| 신규 파일 | 백엔드 11 (마이그레이션 1·도메인 4·인프라 4·테스트 2) / 프론트 7 (상수·유틸·패널·테스트 4) |
| 수정 파일 | 백엔드 8 / 프론트 13 |
| 테스트 추가 | 백엔드 42 (정책 16·use case 14·라우터 12) / 프론트 19 (패널 7·유틸 3·페이지 3·채팅 5) + 기존 픽스처 2 수정 |
| 회귀 | 백엔드 전체 53 failed = 상시 실패 목록과 파일 단위 일치, 신규 0 / 프론트 tsc 210=기준선, eslint 신규 0, vitest 상시 9 + 부하 민감 3파일(단독 통과) |
| 런타임 | 실 DB 스모크 13/13, 브라우저 E2E 등록→저장→채팅 카드→클릭 전송 PASS |
| 반복 | Act-1 1회 (G1·G3·G4) |

### 1.3 Value Delivered

| 관점 | 계획 | 실제 |
|---|---|---|
| **Problem** | 에이전트별 "무엇을 물어볼지" 안내 수단 부재, 모든 에이전트가 같은 고정 카드 4종 | 오프너가 있는 에이전트는 자기 카드, 없으면 기존 카드. super는 불변 |
| **Solution** | 별도 테이블 + additive API + 빌더 탭 + 채팅 분기 | 그대로 구현. 실행 hot path(`find_by_id`)에 쿼리 0 추가, 목록 API는 페이지 슬라이스 후 배치 1쿼리 |
| **UX Effect** | 소유자 등록 12개, 이용자 클릭 즉시 전송 | 브라우저에서 빈 행 포함 3행 저장 → DB 2행, 채팅 카드 2개, 클릭 즉시 전송·응답 스트리밍 확인 |
| **Core Value** | 코어 하드코딩 없는 데이터 기반 온보딩, 회귀 0 | 모든 계약 optional/기본값 → 기존 소비자·MSW·테스트 무변경 통과 |

## 1.4 Success Criteria Final Status

| 기준 (Plan §4.1) | 상태 | 근거 |
|---|---|---|
| FR-01~13 구현 + 테스트 | ✅ | Analysis §2 FR 표, Act-1에서 FR-06 결함 해소 |
| 백엔드 FAILED 목록 diff 0 | ✅ | 53 failed / 10,705 passed — 상시 실패와 일치 |
| 프론트 vitest·lint·tsc 신규 실패 0 | ✅ | tsc 210=기준선, eslint 신규 0, vitest 부하 민감 3파일 단독 통과 |
| 수동 E2E 등록→저장→프라임→채팅 카드→클릭 전송 | ✅ | 2026-10-25 Chrome, "데이터 분석" 에이전트 |
| 오프너 없음·super는 기존 카드 | ✅ | 브라우저 + vitest |
| 위키 미갱신, V080 배포 의존 명시 | ✅ | §8.1 |

**Overall: 6/6**

## 1.5 Decision Record Summary

| 결정 | 출처 | 준수 | 결과 |
|---|---|---|---|
| 별도 테이블 `agent_opener` (JSON 컬럼 아님) | Plan (사용자) | ✅ | V080, FK CASCADE, errno 3780 없이 로컬 적용 |
| 채팅 데이터는 `/agents/my` 목록 응답 확장 | Plan (사용자) | ✅ | 채팅 빈 상태 추가 요청 0, 배치 1쿼리 테스트로 고정 |
| 포크 시 복사 | Plan (사용자) | ✅ | 실 DB 스모크 #11 |
| 12개·200자·중복 422, 정렬 UI 없음 | Plan (사용자) | ✅ (Act-1 후) | 12·200은 Pydantic, 정규화는 도메인 정책 |
| Option C — 포트·리포지토리 분리, sync use case 없음, 엔티티 무변경 | Design (사용자) | ✅ | `AgentDefinition`·`AgentDefinitionRepository` grep 무 hit |
| 라우터 매퍼 함정: 정책 메시지에 "최대/이미/찾을 수 없" 금지 | Design §6.3 | ⚠️→✅ | 고정 문구는 준수했으나 `{text}` 삽입이 구멍(G1). Act-1에서 위치 번호만 쓰도록 수정, Design v0.2 |
| 폼 staged + 상단 저장, 빈 행 조용히 제거 | Design §5.1 | ✅ | `openerPayload.ts`, 브라우저 확인 |
| super는 항상 고정 카드 | Design §5.2 | ✅ | `ChatPage` 분기 + 테스트 |

---

## 2. Related Documents

- Plan: `docs/01-plan/features/agent-opener.plan.md`
- Design: `docs/02-design/features/agent-opener.design.md` (v0.2)
- Analysis: `docs/03-analysis/agent-opener.analysis.md` (v0.2)
- 목표 UI: `docs/img/offner.png`
- 선례: agent-settings-tab(탭 활성화·폼 배선), agent-skill-toggle(자식 테이블·동기화)

---

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 | 근거 |
|---|---|---|---|
| FR-01 | `agent_opener` 테이블 | ✅ | `idt/db/migration/V080__create_agent_opener.sql` |
| FR-02 | 생성 API `openers` 저장 (save 전 정규화) | ✅ | `create_agent_use_case.py` |
| FR-03 | 수정 API None/[]/[...] | ✅ | `update_agent_use_case.py` |
| FR-04 | 상세 응답 `openers` | ✅ | `get_agent_use_case.py` |
| FR-05 | 목록 응답 `openers` 배치 1쿼리 | ✅ | `list_my_agents_use_case.py` `_attach_openers` |
| FR-06 | 12·200·빈·중복 422 | ✅ | Pydantic + `OpenerPolicy`, Act-1 메시지 수정 |
| FR-07 | 포크 복사 | ✅ | `fork_agent_use_case.py` |
| FR-08 | 빌더 오프너 탭 | ✅ | `components/agent-builder/opener/OpenerPanel.tsx` |
| FR-09 | 폼 staged + 상단 저장 | ✅ | `AgentBuilderPage/index.tsx`, `utils/openerPayload.ts` |
| FR-10 | 수정 프라임 | ✅ | `utils/agentDetailMapping.ts` |
| FR-11 | 채팅 빈 상태 분기 | ✅ | `pages/ChatPage/index.tsx`, `components/chat/MessageList.tsx` |
| FR-12 | 클릭 즉시 전송 | ✅ | 기존 `handleSend` 재사용 |
| FR-13 | CASCADE | ✅ (DDL) | 소프트 삭제라 미발동 — Design §1.3 수용 |

### 3.2 Non-Functional Requirements

| 항목 | 기준 | 결과 |
|---|---|---|
| 성능 | 목록 API 오프너 조회 1쿼리 | `batch_calls == 1` 테스트 |
| 호환성 | optional 확장, 기존 테스트 무변경 | 백엔드 1,448 + 프론트 기존 통과 |
| 보안 | 평문 텍스트 렌더 | `<script>` 문자 그대로 렌더 테스트 |
| 데이터 무결성 | COLLATE 미명시·COMMENT 규칙 | DDL 검사 통과, 실 DB 적용 |
| 접근성 | 버튼·입력 aria-label | role 기반 테스트 |

### 3.3 Deliverables

**백엔드 (idt/)**: `db/migration/V080__create_agent_opener.sql`, `src/domain/agent_opener/{schemas,policies,interfaces}.py`, `src/infrastructure/persistence/models/agent_opener/models.py`, `src/infrastructure/agent_opener/agent_opener_repository.py`, `src/application/agent_builder/schemas.py` + 5 use case, `src/api/main.py` DI, `tests/domain/agent_opener/test_opener_policy.py`, `tests/application/agent_builder/test_agent_opener_use_cases.py`, `tests/api/test_agent_builder_router.py`(계약 12건 추가)

**프론트 (idt_front/)**: `constants/agentOpener.ts`, `utils/openerPayload.ts`(+test), `components/agent-builder/opener/OpenerPanel.tsx`(+test), `AgentTestPanel.tsx`, `StudioLayout.tsx`, `pages/AgentBuilderPage/index.tsx`(+test 3), `utils/agentDetailMapping.ts`, `components/chat/MessageList.tsx`, `pages/ChatPage/index.tsx`, `pages/ChatPage/openerCards.test.tsx`, `services/agentSubscriptionService.ts`, `types/{agentBuilder,agent,agentStore}.ts`, 픽스처 2(`composeDraftToForm.test.ts`, `wizardResultToForm.test.ts`)

---

## 4. Incomplete Items

### 4.1 Carried Over (explicit-gap-carryover)

| 항목 | 이유 | 후속 |
|---|---|---|
| G2·G5 실 DI 왕복·리포지토리 실 DB 테스트 | 로컬 MySQL 전용이라 CI 부적합. 스크래치 스모크(`smoke_openers.py`, 13항목)로 2회 검증 | E2E 이월 체크리스트에 "오프너 스모크" 항목 추가 (`/wiki update` 시) |
| G6 Pydantic 배열 `detail`은 "알 수 없는 오류"로 표시 | 기존 `authClient` 인터셉터 동작, 프론트 가드로 사실상 미발생 | 인터셉터 개선 시 함께 |
| `/agents/my` 구독 건별 `find_by_id` N+1 | 기존 결함, 이 기능과 무관 | 별도 소형 사이클 |
| 스트리밍 중 supervisor JSON 원문 노출 | E2E 중 관찰. agent-chat-reasoning-display 영역 | 별도 |
| AutoForkService 오프너 복사 | Plan 범위 밖 | 필요 시 1줄 추가 |

### 4.2 Cancelled

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | Check | Act-1 후 |
|---|---|---|
| Structural | 100% | 100% |
| Functional | 95.2% | 100% |
| Contract | 100% | 100% |
| Runtime | 92.3% (24/26) | 100% (26/26) |
| **Overall** | **96.1%** | **100%** |

### 5.2 Resolved Issues

| # | 내용 | 조치 |
|---|---|---|
| G1 (Important) | 중복 메시지에 사용자 텍스트 포함 → "최대" 등 포함 시 라우터가 409/404 | 위치 번호 기반 메시지, 정책 테스트 4·라우터 테스트 2 추가, 실 DB 5b 422 확인, Design v0.2 |
| G3 | 서버 422 표시·행 유지 테스트 없음 | MSW 422 테스트 추가 |
| G4 | 빈 안내 문구 상이 | Design 문구로 정합 |
| Do 단계 린트 | `OpenerPanel` 렌더 중 ref 접근·미존재 규칙 주석 | 상태로 교체, 주석 제거 |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- **선례 패턴 차용**: agent_skill(자식 테이블·포트) + agent-settings-tab(탭 활성화·폼 staged)을 그대로 따라 설계 단계에서 선택지가 좁아지고 구현이 빨랐다.
- **실런 1회를 모듈 DoD로**: module-1 직후 인프로세스 실 DB 스모크가 DI 5곳 배선·FK 콜레이션을 한 번에 증명했다. 커밋된 테스트는 전부 mock이라 이것이 없었으면 실 DI 결함을 못 잡는다.
- **Design 단계에서 발견한 함정(라우터 문자열 매퍼)을 테스트로 고정**: gap-detector가 그 테스트의 입력이 좁다는 점(`["a","a"]`만)을 잡아 실결함(G1)으로 이어졌다.

### 6.2 Problem
- **Design 메시지 표가 결함의 원인**: `{text}` 삽입을 설계 문서가 명시했고 구현은 충실히 따랐다. "사용자 입력을 에러 메시지에 넣지 않는다"를 규칙으로 두었어야 했다.
- **`git stash`로 린트 기준선 비교**: pop이 bkit 런타임 파일 잠금으로 부분 실패해 복구 작업이 필요했다. 메모리에 이미 "stash 대신 목록 diff" 경고가 있었다.
- **JWT를 앱 기동 전에 발급**: 기동이 15분 넘게 걸린 1회에 전부 401. 기동 후 발급으로 수정.

### 6.3 Try
- 라우터 문자열 매퍼(`_attach_skill_http_error`)를 예외 타입 기반으로 바꾸는 소형 사이클 — 정책 메시지 금칙어 규칙 자체를 없앤다.
- 실 DB 스모크 스크립트를 `tests/manual/`에 보존해 E2E 이월 체크리스트에서 재사용.

---

## 7. Process Improvement Suggestions

| 영역 | 제안 |
|---|---|
| PDCA | Design의 에러 메시지 표에 "사용자 입력 포함 금지" 체크 항목 추가 |
| 도구 | 린트/tsc 기준선 비교는 stash 금지 — 결과 파일 diff로만 (메모리 규칙 재확인) |
| 도구 | gap-detector는 30턴 제한에 걸렸다. 분석 범위가 넓으면 백엔드/프론트로 나눠 두 번 호출 |

---

## 8. Next Steps

### 8.1 Immediate
1. **커밋** — 코드·테스트·문서 전부 미커밋. `main.py` diff는 오프너 전용임을 확인함.
2. **배포 의존**: V080 선행 적용 필수. 미적용 시 `/agents/my`·상세·생성·수정·포크가 `agent_opener` 테이블 부재로 500. `/wiki update` 시 `ops/migration-deploy-deps.md`에 추가.
3. 로컬 DB에는 V080 수동 적용 완료(Flyway 이력 없음). 스모크용 에이전트는 소프트 삭제되어 `agent_opener` 행 잔존(무해).

### 8.2 Next PDCA Cycle
- 라우터 매퍼 예외 타입화 (§6.3)
- `/agents/my` N+1 해소
- 오프너 노출 확장(빌더 테스트 탭 빈 상태·스토어 상세 모달) — Plan 범위 밖으로 둔 항목

---

## 9. Changelog

### v1.0.0 (2026-10-26)
- feat(agent): `agent_opener` 테이블(V080) + 도메인 정책·포트·리포지토리
- feat(api): create/update/get/my/fork에 `openers` additive 확장, DI 5곳
- feat(builder): 오프너 탭 활성화 — `OpenerPanel`, 폼 staged, 상단 저장 통합, 수정 프라임
- feat(chat): 빈 상태 오프너 카드(`SuggestionCards.items`), 클릭 즉시 전송, super·없음은 고정 카드
- fix(domain): 정책 메시지에서 사용자 텍스트 제거 (Check G1)
- test: 백엔드 42 · 프론트 19 추가

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-10-26 | 완료 보고서 |
