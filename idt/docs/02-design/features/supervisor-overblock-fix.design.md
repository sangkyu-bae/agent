# Supervisor Overblock Fix Design Document

> **Summary**: 수퍼바이저 과차단 수정의 구현 설계 — 사용자 컨텍스트 블록의 권한 목록 **완전 제거**(D1) + 위임 가드 문구 교체(D2) + 결정 프롬프트 과차단 금지 지시(D3). 권한 목록 제거로 Plan S3(라벨 매핑 관측성)는 리스크 원천 소멸로 **불필요해짐**(D4)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-22
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/supervisor-overblock-fix.plan.md`

---

## 1. Design Overview

수정 대상은 프롬프트 계층 2개 파일뿐이다. 그래프 구조·결정 스키마·도구 권한 로직은 무변경.

```
render_user_context_block (prompt_rendering.py)     ← D1·D2: 권한 목록 제거 + 위임 가드
        │ prepend (5개 소비처 공통)
        ├── supervisor 결정 프롬프트 (workflow_compiler.py:170 → supervisor_nodes.py)
        │        └── D3: 결정 선택지에 과차단 금지 지시 추가
        ├── data_analysis 노드 (workflow_compiler.py:897)
        ├── excel 워크플로우 (excel_analysis_workflow.py:200)
        ├── general_chat (use_case.py:259)
        └── search rewrite (search_pipeline — rag-auth-filter-fix D5 배선)
```

**영향 범위 실측 (2026-07-22)**:
- 블록 내부 문구를 단언하는 테스트는 `tests/application/agent_run/test_prompt_rendering.py` 3건뿐
  (`권한 라벨`, `(권한 없음)`, `도구가 자동으로 제외`)
- 나머지 소비처 테스트(`test_analyze_user_context.py`, `test_workflow_compiler.py:780-806`,
  `test_memory_injection.py`)는 `[현재 사용자 정보]` 헤더·이름·부서만 단언 — **모두 유지 필드라 무회귀**

---

## 2. D1 — 권한 목록 완전 제거 (격하 아님)

### 2.1 결정

Plan §6.2에서 유보한 "완전 제거 vs 참고용 격하" 중 **완전 제거**를 선택한다.

| 근거 | 설명 |
|------|------|
| 프레이밍 자체가 원인 | "허용된 정보 영역"이라는 목록이 존재하는 한 LLM은 목록 대조를 수행한다. 58-60행의 방어 지시가 이미 있었는데도 패배한 실증이 있음 — 문구 강화(격하)는 같은 패턴의 재발 여지를 남김 |
| 목록의 순기능 부재 | 차단은 도구 3단 방어가 수행하고, 라우팅 판단 재료는 결정 프롬프트의 워커 목록이 별도 제공. 5개 소비처 어디에서도 권한 라벨 목록을 소비하는 로직 없음 (LLM 프롬프트 전용) |
| 리스크 코드 원천 소멸 | 목록 제거 시 `PermissionCode(code).label_ko` 매핑 루프가 통째로 삭제됨 → `(권한 없음)` 오렌더링·조용한 skip 리스크 자체가 사라짐 (→ D4) |
| PII 표면 축소 | 권한 목록도 사용자 속성 노출임 — 제거는 whitelist 원칙(§4.3)과 방향 일치 |

**트레이드오프 수용**: "내가 뭘 할 수 있어?" 류 질의에 권한 목록 기반 답변 불가 —
수퍼바이저의 워커 목록으로 기능 안내는 가능하므로 수용 (Plan 리스크 1 완화 근거와 동일).

### 2.2 prompt_rendering.py 변경

```python
# 삭제: PermissionCode import, perm_labels 루프(42-48행), "[허용된 정보 영역]" 섹션(56-57행)
# 유지: 헤더·이름·부서·역할·'나' 해석 규칙, anonymous/None → "" (FR-04)
# 교체: 마지막 지시 3줄(58-60행) → 위임 가드 문구 (D2)
```

`PermissionCode`/`label_ko`는 domain에 유지 (다른 소비처·테스트 `test_value_objects.py` 무변경 —
prompt_rendering이 더 이상 import하지 않을 뿐).

---

## 3. D2 — 위임 가드 문구 (블록 신규 전문)

```text
[현재 사용자 정보]
- 이름: {display_name}
- 부서: {dept or (미배정)}
- 역할: {관리자|일반 사용자}

사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.

정보 접근 권한은 각 도구가 자동으로 검증하고 필터링합니다.
권한이나 개인정보 보호를 이유로 요청을 거부하거나 차단하지 마세요.
도구의 검색 결과에 없는 내용은 '확인되지 않습니다'라고 답하세요.

---

```

문구 설계 근거:
- "권한이 없는 정보는 도구가 자동으로 제외합니다"(구) → "각 도구가 자동으로 검증하고 필터링합니다"(신):
  구 문구는 "권한이 없는 정보"라는 존재를 전제해 심사를 유도 — 신 문구는 책임 소재만 진술
- "거부하거나 차단하지 마세요"는 첨부 블록 선례(`supervisor_nodes.py:37` "권한이 없다고 거부하지 말고")와
  동일 강도의 부정 명령형
- "확인되지 않습니다" 폴백 지시는 유지 — 권한 밖 데이터는 도구 필터로 검색 결과에서 빠지므로
  이 지시가 사실상의 안전망 (Plan 리스크 1 완화)

---

## 4. D3 — 결정 프롬프트 과차단 금지 지시

`supervisor_nodes.py` `decision_prompt`(200-214행)의 선택지 리스트에서
"처리 가능한 워커가 ... 거부하지 말고 그 워커를 선택" 항목 **직후**에 1줄 추가:

```python
f"- 처리 가능한 워커가 사용 가능 목록에 있으면 거부하지 말고 그 워커를 선택\n"
f"- 권한·개인정보 보호는 각 워커의 도구가 자동으로 검증하므로, 그것을 이유로 "
f"'FINISH'를 선택하지 마세요. 관련 정보를 찾을 가능성이 있는 워커가 있으면 "
f"먼저 라우팅하세요\n"          # ← 신규 (supervisor-overblock-fix D3)
```

- **양쪽 배치의 이유** (Plan §6.2 확정): 컨텍스트 블록은 `include_user_context=False`(system bot)나
  `auth_ctx=None`이면 prepend되지 않음 — 결정 프롬프트 지시는 모든 경로에서 유효한 단일 방어선
- FINISH+answer 처리 로직(240-252행)·`SupervisorDecision` 스키마·라우팅은 무변경 (FR-05)

---

## 5. D4 — Plan S3(라벨 매핑 관측성) 소멸 처리

Plan FR-03은 "라벨 변환 실패 시 warning 로그"였으나, D1(완전 제거)로 **매핑 코드 자체가 삭제**되어
실패 경로가 존재하지 않게 됨 → 로그 추가 불필요. optional logger 파라미터 주입(Plan 리스크 5)도 무산 —
`render_user_context_block`은 순수 함수로 유지된다.

- enum↔DB seed 불일치의 실태 파악 가치는 남지만, 프롬프트 경로와 무관해졌으므로 본 기능 범위에서 제외
  (Plan §9-4 후속 검토 항목은 "필요 시 별도 기능"으로 대체)

---

## 6. 테스트 설계 (TDD 순서)

### 6.1 test_prompt_rendering.py 갱신

| TC | 종류 | 내용 |
|----|------|------|
| 삭제 | `test_includes_korean_permission_labels` | 권한 라벨 노출 자체가 사라짐 |
| 삭제 | `test_no_permissions` | `(권한 없음)` 렌더링 소멸 |
| 삭제 | `test_unknown_permission_code_skipped` | 매핑 루프 소멸 |
| **신규** | `test_permission_list_not_exposed` | `"허용된 정보 영역" not in block` + 권한 라벨(예: "RAG 문서 검색") 부재 — permissions를 채운 ctx로 검증 (FR-01 시맨틱 단언) |
| **신규** | `test_includes_delegation_guard` | "거부하거나 차단하지 마세요" + "확인되지 않습니다" 포함 (D2) |
| 수정 | `test_includes_no_block_self_decision_warning` | 단언 문구를 "도구가 자동으로 검증" 신규 문구로 교체 |
| 유지 | Happy(이름·부서·역할·'나' 규칙), Edge(anonymous/None/미배정), Security 전부, Deterministic | FR-04 + whitelist 불변 검증 |

### 6.2 supervisor 결정 프롬프트 조립 테스트 (신규 파일 `test_supervisor_overblock.py`)

`test_supervisor_data_context.py`의 캡처 패턴(mock LLM에 전달된 system 메시지 검사) 재사용:

| TC | 내용 |
|----|------|
| TC-O01 | 결정 프롬프트에 "'FINISH'를 선택하지 마세요" 과차단 금지 지시 포함 (FR-02) |
| TC-O02 | FINISH+answer+워커 미실행 경로 기존 동작 보존 — 단순 인사 등 정당한 직접 응답 (FR-05, 기존 TC-S02와 동일 패턴) |

E2E(FR-06)는 수동 실측 — run 상세 supervisor step `output_summary` 확인 (Plan §8.2).

---

## 7. 구현 순서

```
1. RED   test_prompt_rendering.py 갱신 (6.1) → 실패 확인
2. GREEN prompt_rendering.py 수정 (D1·D2)
3. RED   test_supervisor_overblock.py 신규 (6.2) → 실패 확인
4. GREEN supervisor_nodes.py 결정 프롬프트 수정 (D3)
5. 관련 테스트 격리 실행 (agent_run + agent_builder) → 전체 무회귀 확인
6. E2E 수동: "나의 남은 휴가 개수" 질의 → 첫 결정이 검색 워커인지 실측 (FR-06)
```

---

## 8. 리스크·영향 재확인

| 항목 | 판정 |
|------|------|
| general_chat/analysis/excel/search rewrite 등 타 소비처 | 블록 공유로 동일하게 권한 목록이 빠짐 — 이들 경로에도 자체 심사 유도 요인이 제거되는 **의도된 개선**. 소비처 테스트는 헤더·이름만 단언(실측)이라 무회귀 |
| 스냅샷 광범위 파손 (Plan 리스크 4) | 실측 결과 내부 문구 단언은 3건뿐 — 시맨틱 단언으로 교체 (6.1) |
| API/스키마/마이그레이션 | 없음 — 프롬프트 문자열만 변경, 프론트 동기화 불필요 |
| 아키텍처 | prompt_rendering은 domain import만 유지(순수 함수 유지, D4로 로거 주입 무산) — 레이어 규칙 준수 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-22 | Initial — D1 완전 제거 확정(격하 기각), D4로 Plan S3 소멸 처리, 영향 범위 실측 반영 | 배상규 |
