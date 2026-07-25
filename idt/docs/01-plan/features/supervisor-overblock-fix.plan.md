# Supervisor Overblock Fix Planning Document

> **Summary**: 커스텀 에이전트 수퍼바이저가 개인 데이터 질의("나의 휴가")에 워커 라우팅 없이 **자체 권한 판단으로 즉시 거부**(FINISH+answer)하는 과차단 결함 수정 — 사용자 컨텍스트 블록의 권한 목록 프레이밍 완화 + 결정 프롬프트 라우팅 우선 지시 + 권한 라벨 매핑 누락 관측성
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-22
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 첫 채팅 진입 시 수퍼바이저 LLM이 "사용자의 휴가 정보는 개인 정보에 해당하며, 현재 제공된 권한 내에서는 접근할 수 없습니다"라고 스스로 작문한 answer와 함께 FINISH를 선택 — 검색 워커가 목록에 있는데도 호출 자체가 일어나지 않음. 원인은 시스템 프롬프트 앞에 prepend되는 `[허용된 정보 영역]` 권한 라벨 목록이 수퍼바이저를 권한 심사관으로 프레이밍하는 것. 실제 권한 차단은 도구 내부 3단 방어(USE_RAG_SEARCH 차단 + visibility 필터)가 이미 수행하므로 상류의 중복 심사는 순수 과차단 |
| **Solution** | ① 사용자 컨텍스트 블록에서 권한 목록의 게이트 프레이밍 제거·재구성("허용된 정보 영역" → 도구 참고 정보로 격하 또는 노출 제거) ② 수퍼바이저 결정 프롬프트에 "권한 판단은 도구 책임 — 처리 가능성이 있으면 워커로 라우팅" 명시 지시 추가 ③ 권한 코드→한국어 라벨 변환 실패 시 조용히 skip되어 `(권한 없음)`으로 렌더링될 수 있는 결함에 관측성(경고 로그) 부여 |
| **Function/UX Effect** | "나의 휴가 몇 개 남았어?" 같은 개인 데이터 질의가 거부 문구 대신 검색 워커 → (권한 필터 적용된) 검색 결과 → 분석/답변 경로를 정상 주행. 권한이 실제로 없는 경우에도 상류 작문 거부가 아니라 도구의 일관된 거부/필터 결과("검색 결과에 없음")로 수렴 |
| **Core Value** | 권한 방어의 단일 책임 원칙 복원 — 차단은 도구(3단 방어)가, 라우팅은 수퍼바이저가. LLM 자유 작문에 의존하던 비결정적 거부를 제거해 rag-auth-filter-fix로 복구한 검색 가치사슬(KB 업로드→검색→분석→시각화)이 첫 관문에서 끊기지 않게 보장 |

---

## 1. Overview

### 1.1 Purpose

수퍼바이저가 워커 실행 전에 자체 권한 판단으로 FINISH를 선택해 검색 가능한 질의를 거부하는
과차단(overblock)을 수정한다. 권한 차단의 실체는 하류 도구(`InternalDocumentSearchTool` 3단 방어)에
이미 있으므로, 상류(수퍼바이저)는 라우팅 판단에 집중하도록 프롬프트 계층을 재정렬한다.

### 1.2 Background (2026-07-22 코드 추적으로 원인 확정)

**증상**: 커스텀 에이전트 첫 턴에서 수퍼바이저가 워커 호출 없이
"사용자의 휴가 정보는 개인 정보에 해당하며, 현재 제공된 권한 내에서는 접근할 수 없습니다.
따라서 사용자의 요청을 처리할 수 없습니다." 를 최종 답변으로 반환.

**메시지 생성 경로 (코드에 없는 문구 — LLM 자체 작문)**:

- `supervisor_nodes.py:240-252`: LLM이 `FINISH` + `answer`를 반환하고 `last_worker_id`가 비어 있으면(첫 턴)
  그 answer가 `AIMessage`로 그대로 최종 답변이 되며 **final_answer 노드도 우회**한다.
- 즉 거부 문구는 가드레일 코드가 아니라 `SupervisorDecision.answer` 필드의 LLM 작문.

**LLM이 거부를 선택하게 만든 원인 체인**:

1. **권한 목록 프레이밍** — `workflow_compiler.py:170-177`이 `render_user_context_block(auth_ctx)`
   (`prompt_rendering.py:50-62`)을 supervisor_prompt 앞에 prepend. 블록의 `[허용된 정보 영역]` 섹션이
   사용자 권한 라벨 목록을 노출하고, "휴가 정보"는 어떤 라벨에도 명시되지 않아 LLM이
   "제공된 권한 밖"으로 추론. 거부 문구의 "현재 제공된 권한 내에서는"이 이 블록을 읽었다는 직접 증거.
   58-60행의 방어 지시("권한 여부를 직접 판단해서 차단하지 말고")가 이미 존재하나 목록 프레이밍에 패배.
2. **결정 지시의 거부 유도 조건** — `supervisor_nodes.py:209-210`
   "어떤 워커로도 처리할 수 없을 때만 'FINISH'를 선택하고 answer 작성"이
   "권한이 없어 처리 불가"라는 자체 추론과 결합하면 정확히 거부 경로가 됨.
   208행의 "처리 가능한 워커가 있으면 거부하지 말고 선택" 지시는 권한 프레이밍보다 약함.
3. **워커 설명의 커버리지 부족** — `internal_document_search` 설명은 "내부 정책/지식 기반 질의"
   (`tool_registry.py:29-30`)로, 개인/인사 데이터 질의를 처리할 수 있다는 신호가 없음.
4. **잠재 악화 요인: `(권한 없음)` 렌더링** — `prompt_rendering.py:42-48`에서 권한 코드가
   `PermissionCode` enum 변환에 실패하면(`ValueError`) **조용히 skip**. DB seed와 enum 불일치 시
   실제 권한 보유자도 `- (권한 없음)`으로 렌더링될 수 있고, 이 경우 거부가 사실상 확정됨.
   현재 로그 없음 → 발생 여부 관측 불가.

**하류 방어 현황 (중복 심사 불필요의 근거)**:

- 도구 1차: `USE_RAG_SEARCH` 미보유 시 즉시 거부 (`tools.py:179`)
- 도구 2차: `_apply_auth_filter`가 visibility/부서 필터 주입 (`tools.py:152-169`)
- 도구 3차: HybridSearch/Qdrant/ES 필터 적용 (rag-auth-filter-fix에서 lenient 정합화 완료)
- 컨텍스트 블록 자체도 "권한이 없는 정보는 도구가 자동으로 제외합니다"라고 이미 명시 — 설계 의도는
  본래 "수퍼바이저는 심사하지 않는다"였으나 프롬프트 구조가 의도를 관철하지 못함.

### 1.3 Related Documents

- 사용자 컨텍스트 블록 도입: agent-user-context Design §4.3 (`prompt_rendering.py` docstring)
- 하류 권한 방어: `docs/01-plan/features/rag-auth-filter-fix.plan.md` (§1.2 3단 방어)
- 첨부 시 유사 선례: `supervisor_nodes.py:21-38` `_render_attachment_block` —
  "권한이 없다고 거부하지 말고 반드시 그 워커로 라우팅하세요" 지시를 이미 사용 중 (이번 수정의 문구 선례)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 사용자 컨텍스트 블록 재구성**: `[허용된 정보 영역]` 권한 목록의 게이트 프레이밍 제거.
      이름·부서·역할("나"의 해석 규칙)은 유지하되, 권한 목록은 노출 제거 또는
      "시스템 참고용 — 라우팅/답변 차단 판단에 사용 금지" 프레이밍으로 격하 (방식은 Design에서 확정)
- [ ] **S2. 결정 프롬프트 라우팅 우선 지시**: 수퍼바이저 결정 선택지에
      "권한/개인정보 여부는 도구가 검증·필터링하므로 그 이유로 FINISH를 선택하지 말 것 —
      처리 가능성이 있는 워커가 있으면 라우팅" 명시 (첨부 블록의 기존 문구 패턴 재사용)
- [ ] **S3. 권한 라벨 매핑 누락 관측성**: enum 변환 실패로 라벨이 skip될 때 warning 로그
      (누락 코드 목록 포함) — `(권한 없음)` 오렌더링의 발생 여부를 운영에서 추적 가능하게
- [ ] **S4. 회귀 테스트**: ① 컨텍스트 블록 렌더링 단언(권한 게이트 문구 부재, 유지 필드 존재)
      ② 수퍼바이저 결정 프롬프트 조립 단언(라우팅 우선 지시 포함) ③ 기존 스냅샷/조립 테스트 갱신
- [ ] **S5. E2E 수동 검증**: "나의 남은 휴가" 질의가 첫 턴에 검색 워커로 라우팅되는지
      run step(`output_summary`) 실측 확인

### 2.2 Out of Scope

- 도구 레이어 권한 로직 변경 (rag-auth-filter-fix에서 완료 — 무변경)
- `PermissionCode` enum·DB seed 자체의 불일치 수정 (S3 로그로 실태 파악 후 필요 시 후속)
- 워커 설명(`tool_registry.py`) 문구 개선 — 에이전트별 tool_config/description 정책과 얽혀 있어
  효과 확인 후 후속 판단 (이번엔 프롬프트 계층으로 해결)
- 수퍼바이저 구조 변경(결정 스키마, 라우팅 그래프) — 프롬프트 텍스트와 로그만 수정
- 프론트엔드 변경 (백엔드 전용 — API 계약 불변)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 사용자 컨텍스트 블록에 권한 목록이 "허용된 정보 영역"(접근 가능 범위) 프레이밍으로 노출되지 않는다. 이름·부서·역할·"나" 해석 규칙은 유지된다 | High | Pending |
| FR-02 | 수퍼바이저 결정 프롬프트에 "권한·개인정보를 이유로 한 FINISH 금지, 도구가 필터링함" 지시가 포함된다 | High | Pending |
| FR-03 | 권한 코드→라벨 변환 실패 시 누락 코드 목록이 warning 로그로 남는다 (graceful skip 동작 자체는 유지) | Medium | Pending |
| FR-04 | 미인증(anonymous)·auth_ctx=None 경로의 기존 동작(빈 블록)은 불변이다 | High | Pending |
| FR-05 | 워커가 실행된 런의 FINISH 처리(answer 폐기·final_answer 경유)는 기존 동작 불변이다 | High | Pending |
| FR-06 | "나의 X" 개인 데이터 질의 시나리오에서 첫 결정이 검색 워커 라우팅이 된다 (E2E 수동 — run step 실측) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 안전 | 기존 pytest 무회귀 (사전 실패분 제외 기준), 프롬프트 조립·렌더링 테스트 갱신 범위 최소화 | pytest 격리 실행 |
| 아키텍처 | 프롬프트 렌더링은 application 레이어 유지, 로거는 인터페이스 주입 — 레이어 규칙 준수 | verify-architecture 스킬 |
| PII | 컨텍스트 블록 whitelist(user_id/사번/이메일 금지) 불변 | 렌더링 테스트 단언 |
| TDD | 테스트 선행 (Red → Green → Refactor) | verify-tdd 스킬 |
| 로깅 | 신규 로그 LOG-001 준수 (structured, print 금지) | verify-logging 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현 시나리오: "나의 남은 휴가 개수" 질의 첫 턴에 수퍼바이저가 거부 answer 없이
      검색 워커를 선택 (run 상세 supervisor step `output_summary` 실측)
- [ ] 권한이 실제 없는 사용자(USE_RAG_SEARCH 미보유)는 도구 거부 메시지 경로로 일관 처리됨
- [ ] 렌더링/조립 신규 테스트 전부 통과 + 기존 테스트 무회귀
- [ ] 라벨 매핑 누락 시 warning 로그 확인 (테스트로 검증)

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 하드코딩 config 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 권한 목록 제거로 LLM이 답변 범위 힌트를 잃어 오히려 과응답(권한 밖 주제 시도) | Low | Medium | 차단 실체는 도구 3단 방어가 담당 — 검색 결과에 없으면 "확인되지 않습니다" 지시 유지. 프롬프트는 정보 축소가 아니라 프레이밍 교정 |
| 프롬프트 변경이 다른 라우팅 판단(분석/차트 경로)에 회귀 유발 | Medium | Low | 결정 선택지 구조는 불변, 문구 추가만. 기존 조립 테스트 + 첨부/시각화 블록 테스트로 확인 |
| LLM 비결정성으로 E2E 검증이 불안정 | Medium | Medium | 단위 검증은 프롬프트 조립 단언으로 결정적으로 수행, E2E는 보조 실측(FR-06)으로 한정 |
| 컨텍스트 블록 스냅샷 테스트 광범위 파손 | Low | High(의도됨) | 기대값 갱신은 FR-01 시맨틱 단언(게이트 문구 부재)과 함께 갱신 — 단순 스냅샷 덮어쓰기 금지 |
| prompt_rendering에 로거 주입 시 순수 함수 계약 변경 | Low | Medium | 로거는 optional 파라미터(기본 None → 무로그)로 additive 주입 — 기존 호출부 무변경 (독립 opt-in 관례 준수) |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 권한 목록 처리 | 완전 제거 / 프레이밍 격하(참고용 명시) | Design에서 확정 | 제거가 단순하나, "권한 밖 주제엔 검색 후 '확인되지 않음'" 흐름에 라벨이 기여하는지 Design에서 판단 |
| 과차단 방지 지시 위치 | 컨텍스트 블록 / 결정 프롬프트 / 양쪽 | 양쪽 (S1+S2) | 블록은 include_user_context=False면 빠짐 — 결정 프롬프트에도 있어야 무권한 컨텍스트 경로 커버 |
| 라벨 누락 대응 | 조용히 skip 유지 / raw 코드 노출 / skip+로그 | skip + warning 로그 | LLM에 raw 코드 노출은 무의미·혼란. 관측성만 확보 후 seed 불일치는 별도 수정 |
| 도구 설명 개선 | 이번 포함 / 후속 | 후속 | 프롬프트 계층 수정만으로 효과 확인 먼저 — 변경 반경 최소화 |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── application/agent_run/prompt_rendering.py      # S1·S3: 블록 재구성, 라벨 누락 로그(optional logger)
├── application/agent_builder/supervisor_nodes.py  # S2: 결정 프롬프트 라우팅 우선 지시
└── tests/
    ├── application/agent_run/ (렌더링 테스트)      # S4: FR-01/03/04 단언
    └── application/agent_builder/ (조립 테스트)    # S4: FR-02/05 단언
```

> 정확한 프롬프트 문구·권한 목록 처리 방식은 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] 검증 스킬 존재: verify-architecture, verify-logging, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness)
- 환경변수·마이그레이션·API 계약 변경 **없음** (프론트 동기화 불필요)

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-01/04  컨텍스트 블록 재구성: 렌더링 테스트 먼저 (게이트 문구 부재·유지 필드·anonymous 불변) → prompt_rendering 수정
2. FR-02/05  결정 프롬프트 지시 추가: 조립 테스트 먼저 → supervisor_nodes 수정
3. FR-03     라벨 누락 warning 로그 (optional logger 주입)
4. 전체 pytest 무회귀 + FR-06 E2E 수동 실측 (run step output_summary)
```

### 8.2 검증 자료

- 검증 경로: `GET /agents/runs/{run_id}` supervisor step `output_summary`(= `decision.reasoning`),
  LangSmith `agent-run` 프로젝트의 결정 프롬프트 전문
- 재현 질의: "나의 남은 휴가 개수와 월별 사용 현황" (rag-auth-filter-fix §8.2와 동일 시나리오 —
  하류 검색 히트까지 연결 확인 가능)

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design supervisor-overblock-fix`) — 권한 목록 처리 방식(제거 vs 격하)·프롬프트 문구 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze supervisor-overblock-fix`)
4. [ ] 후속 검토: PermissionCode↔DB seed 불일치 실태 (S3 로그 관측 결과에 따라)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-22 | Initial draft — 수퍼바이저 FINISH 경로·프롬프트 프레이밍 원인 코드 추적 기반 | 배상규 |
