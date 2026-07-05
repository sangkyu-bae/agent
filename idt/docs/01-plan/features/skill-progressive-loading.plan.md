# Plan: skill-progressive-loading

> Created: 2026-06-30
> Phase: Plan
> Scope: `idt/` 백엔드 — 에이전트 부착 Skill의 supervisor_prompt 주입을 "전체 항상 주입(eager)"에서 "관련 스킬만 선택 주입(점진/방식 A)"으로 전환. 추후 "모델 주도 on-demand 로딩(방식 B)"으로 무리 없이 진화 가능한 구조로 설계.

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 현재 `RunAgentUseCase._inject_attached_skills`는 에이전트에 부착된 Skill의 `instruction` 전문을 **매 실행마다 전부** supervisor_prompt 앞에 prepend한다(`SkillInjectionPolicy.merge`). 부착 스킬이 늘수록 매 호출 입력 토큰이 선형 증가하고, 그래서 `MAX_ATTACHED=3`으로 묶여 있다. 질문과 무관한 스킬도 항상 켜져 비용·프롬프트 비대화·스킬 확장성 제약을 유발한다. |
| **Solution** | **방식 A(관련성 게이트 주입)**: 질문(query)을 기준으로 부착 스킬 중 관련된 것만 골라(`SkillResolver`) instruction을 주입한다. 핵심은 `list_attached_skills`가 **이미 `description`/`trigger`를 함께 반환**한다는 점 — DB 스키마 변경 없이 메타데이터로 선택이 가능하다. 동시에 반환 구조를 `ResolvedSkills{injected, catalog, deferred}`로 정의해, 나중에 **방식 B(catalog 상시 노출 + `load_skill` 모델 주도 로딩)** 가 필드만 채우면 되도록 진화 seam을 미리 둔다. |
| **Function/UX Effect** | 사용자 답변 품질은 동일하거나 향상(관련 스킬만 명확히 주입)되며, 무관 스킬 미주입으로 매 턴 입력 토큰·지연이 감소한다. 점진 로딩이 전제되면 `MAX_ATTACHED`를 안전하게 상향(예: 3→15)할 수 있어 스킬 확장성이 열린다. |
| **Core Value** | "부착하면 항상 켜짐"을 "필요할 때만 켜짐"으로 전환해 비용·확장성 동시 개선. A는 라우팅 아키텍처에 맞는 최소 변경으로 즉시 효과를 내고, B(진짜 모델 주도)로 가는 길을 막지 않는 구조를 확보한다. |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 동작 (eager injection)

실행 시 `RunAgentUseCase._prepare_graph → _inject_attached_skills`가 다음을 수행한다 (`src/application/agent_builder/run_agent_use_case.py:485-512`):

```
skills = await agent_skill_repo.list_attached_skills(agent.id, request_id)   # 부착 전체
injectables = [InjectableSkill(name=s.name, instruction=s.instruction, sort_order=i) ...]
merged = SkillInjectionPolicy.merge(workflow.supervisor_prompt, injectables) # 전부 prepend
```

- `SkillInjectionPolicy.merge`는 부착 스킬 instruction을 `sort_order` 순으로 **전부** supervisor_prompt 앞에 붙인다 (`src/domain/agent_skill/policies.py:42-65`).
- 총 길이 가드 `MAX_TOTAL_INJECTED=40,000`자 초과분은 **조용히 drop**(로그 없음).
- 부착 개수 상한 `MAX_ATTACHED=3` — 주석에 "프롬프트 비대화 방지"라고 명시(`policies.py:12`). 즉 상한 자체가 eager 주입의 부작용을 막기 위한 임시방편.

### 1-2. 핵심 비효율

1. **항상 주입**: 질문과 무관한 스킬도 매 run마다 system prompt에 들어가 입력 토큰을 상시 소비.
2. **확장 불가**: 토큰 부담 때문에 3개로 묶임 → 실제 스킬 라이브러리 확장이 막힘.
3. **선택 신호 폐기**: 선택에 쓸 수 있는 메타가 이미 있는데도 안 쓴다(아래).

### 1-3. 결정적 발견 — 선택용 메타데이터가 이미 존재

`AgentSkillRepository.list_attached_skills`는 `agent_skill ⨝ skill_definition` 조인으로 **`SkillDefinition` 전체**를 반환한다 (`src/infrastructure/agent_skill/agent_skill_repository.py:81-97`). `SkillDefinition`은 이미 다음을 보유 (`src/domain/skill_builder/schemas.py:19-41`):

| 필드 | 용도(점진 로딩 관점) |
|------|----------------------|
| `name` | 카탈로그/주입 헤더 |
| `description` | **선택 신호(트리거 요약)** — 현재 미사용 |
| `trigger` | **선택 신호(발동 조건)** — 현재 미사용 |
| `instruction` | 본문(선택된 스킬만 주입) |

→ 현재 `_inject_attached_skills`는 `name`+`instruction`만 쓰고 `description`/`trigger`를 **버린다**. **방식 A는 DB 변경·마이그레이션 없이** 이 두 필드를 선택 신호로 쓰면 된다.

---

## 2. 목표 / 비목표

### 2-1. 목표
- **G1.** 부착 스킬 전체 주입 → **query 관련 스킬만 선택 주입**(방식 A). 무관 스킬 instruction은 미주입.
- **G2.** 선택은 이미 로딩된 `description`/`trigger`를 신호로 사용 — **DB 스키마/마이그레이션 변경 없음**.
- **G3.** 주입 결과를 `ResolvedSkills{injected, catalog, deferred}` 구조로 표준화해 **방식 B 진화 seam**을 확보(B는 필드만 채우면 됨).
- **G4.** **완전한 하위호환**: 기능 플래그 off 또는 resolver 미주입 시 현재 "전부 주입" 동작 100% 유지.
- **G5.** 점진 로딩 전제 하에 `MAX_ATTACHED` 상향 가능(플래그 연동, 기본값/상향값은 Design에서 확정).
- **G6.** 아키텍처/로깅 검증 + TDD 테스트.

### 2-2. 비목표 (이번 범위 제외)
- **N1.** 방식 B 구현(`load_skill` tool / `skill_loader` route 노드, catalog 상시 노출 발동). — 본 Plan은 B로의 **seam만** 만든다.
- **N2.** Skill CRUD(skill_builder) API/UI 변경. `description`/`trigger`는 이미 존재하므로 입력 UX 개선은 후속.
- **N3.** 서브에이전트 경로 스킬 주입(현재 최상위만 주입 — 별도 이슈로 분리).
- **N4.** 대화 멀티턴에 걸친 "한 번 켠 스킬 유지" 상태관리(매 run query 기준 재선택 유지).

---

## 3. 해결 방안

### 3-1. 방식 비교 (직전 논의 정리)

| 방식 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A (이번 채택)** | 선택기(`SkillResolver`)가 query로 관련 스킬만 골라 instruction 주입. supervisor는 그대로 system prompt로 수신. | 라우팅 아키텍처(=supervisor는 tool 호출 노드 아님)에 자연 정합. 변경 국소적. 즉시 토큰 절감 + cap 상향 가능. DB 변경 0. | 진짜 모델 주도 아님(선택기가 대신 판단). run당 선택 비용(임베딩이면 ~0, LLM 분류면 호출 1회). |
| **B (후속)** | catalog(name+description+trigger)만 상시 노출, 본문은 `load_skill` tool/route로 **모델이 필요 시** 로딩. | Claude Code 의미에 충실(모델 주도·지연 로딩·런 중 로딩). | supervisor가 tool 호출 노드가 아니라 그래프 변경 필요. instruction이 system이 아닌 message로 유입 → steering 약화. 비용 대비 실익 애매. |

**채택: A. 단, 반환 구조를 B와 공유하도록 설계**하여 후속 전환 시 A의 산출물을 그대로 재사용.

### 3-2. A→B 진화 seam (핵심 설계)

선택 결과를 단일 표준 구조로 정의한다(application/domain):

```
ResolvedSkills:
  injected: list[InjectableSkill]   # 지금 supervisor_prompt에 prepend (A가 채움)
  catalog:  str                     # name+description+trigger 경량 목록 (B가 상시 노출용으로 채움)
  deferred: list[InjectableSkill]   # on-demand 로딩 후보 (B가 load_skill용으로 채움)
```

- **방식 A 구현(`RelevanceGatedResolver`)**: `injected = 선택된 스킬`, `catalog = ""`(또는 선택 스킬 name만), `deferred = []`.
- **방식 B 구현(후속 `OnDemandResolver`)**: `injected = []`, `catalog = 전체 카탈로그`, `deferred = 전체 스킬` → 그래프가 `deferred`로 `load_skill` 등록.

호출부(`run_agent_use_case`)는 `injected`(+추후 `catalog`) 만 소비하고, 컴파일러는 추후 `deferred`만 소비. **A 시점에 구조를 박아두면 B는 순수 additive**가 된다.

### 3-3. 선택기(`SkillResolver`) 전략 — Design에서 1차 확정

| 후보 | 방식 | 장점 | 단점 |
|------|------|------|------|
| **임베딩(권장 1순위)** | `description`+`trigger` 임베딩 vs query 코사인 + threshold/top_k | 추가 LLM 호출 0(또는 임베딩 1회), 결정적·저렴 | 임베딩 캐싱/저장 필요. 미묘한 트리거 판단 약할 수 있음 |
| **경량 LLM 분류** | query + catalog → 고를 스킬 name 구조화 출력. 기존 `pipeline_llm`(search 파이프라인 경량 모델) 재사용 가능 | 트리거 의미 판단 정확 | run당 LLM 호출 1회(지연·비용) |
| **휴리스틱(fallback)** | `trigger` 키워드 substring 매칭 | 무비용 | 정밀도 낮음 |

> 1차는 **임베딩** 또는 **휴리스틱+경량 LLM 하이브리드** 중 택1. resolver는 인터페이스 뒤에 두어 교체 가능하게 한다.

---

## 4. 목표 아키텍처 (방식 A)

```
RunAgentUseCase._prepare_graph
  └ _inject_attached_skills(workflow, agent, request)        ← query 전달 추가
       skills = list_attached_skills(agent.id)               (description/trigger 포함)
       resolved = await skill_resolver.resolve(query, skills) → ResolvedSkills
       merged = SkillInjectionPolicy.merge(supervisor_prompt, resolved.injected)
       (B 후속) catalog 있으면 경량 카탈로그도 prepend / deferred는 compiler로 전달
  └ compiler.compile(workflow=merged 적용)                   (변경 없음)
```

### 4-1. 레이어 배치 (CLAUDE.md DDD 준수)

| 레이어 | 추가/변경 | 내용 |
|--------|-----------|------|
| **domain** | `agent_skill/policies.py` | `SkillInjectionPolicy.merge` 재사용. 신규 순수 헬퍼 `build_catalog(skills)->str`(B 대비), 선택 임계 상수. `ResolvedSkills` dataclass. |
| **domain** | `agent_skill/interfaces.py` (또는 신규 `skill_resolver` 인터페이스) | `SkillResolverInterface.resolve(query, candidates)->ResolvedSkills` 포트 정의. |
| **application** | `run_agent_use_case.py` | `_inject_attached_skills`에 `query` 인자 추가 + resolver 호출. resolver 미주입 시 기존 동작 fallback. |
| **infrastructure** | 신규 `infrastructure/agent_skill/skill_resolver.py` | `RelevanceGatedResolver`(임베딩/LLM/휴리스틱 중 택1) 구현. |
| **config/조립** | `config.py` + `api/main.py` | 기능 플래그·threshold·top_k·`MAX_ATTACHED` 상향값. resolver DI 주입. |

### 4-2. 하위호환 가드
- `skill_resolver`가 None → 현 동작(전부 주입) 유지. (`agent_skill_repo is None`과 동일 패턴)
- 기능 플래그 off → resolver 호출 생략하고 전부 주입.
- resolver가 0개 반환 시 정책: **Design Open Question(8-3)** — (a) 안전하게 전부 주입 fallback vs (b) 미주입(토큰 우선). 기본은 (a) 권장.

---

## 5. 영향 범위 (Affected Files)

| 파일 | 변경 |
|------|------|
| `src/domain/agent_skill/policies.py` | `ResolvedSkills` dataclass, `build_catalog()` 순수 헬퍼, 선택 임계 상수 추가. `merge`는 유지. |
| `src/domain/agent_skill/interfaces.py` | `SkillResolverInterface` 포트 추가(또는 신규 파일). |
| `src/application/agent_builder/run_agent_use_case.py` | `_inject_attached_skills(query 추가)` → resolver 호출, merge는 `resolved.injected`만. resolver 미주입 fallback. |
| `src/infrastructure/agent_skill/skill_resolver.py` (신규) | `RelevanceGatedResolver` 구현(선택 전략). |
| `src/config.py` | `skill_progressive_loading_enabled`, threshold/top_k, `MAX_ATTACHED` 상향값(플래그 연동). |
| `src/api/main.py` | resolver 생성·DI 주입, `RunAgentUseCase`에 전달. |
| `src/domain/agent_skill/policies.py::SkillAttachPolicy.MAX_ATTACHED` | 플래그 on일 때 상향 허용(상수 직접 변경 대신 정책 인자/설정화 검토). |

### 5-1. 테스트 영향 (TDD)
- `tests/domain/agent_skill/` — `build_catalog`, `ResolvedSkills`, merge 회귀(순수 단위).
- 신규 `tests/infrastructure/agent_skill/test_skill_resolver.py` — query별 선택 결과(관련 선택/무관 제외/0개/threshold 경계).
- `tests/application/agent_builder/test_run_agent_use_case_*` — resolver 주입 시 선택 주입, 미주입 시 전부 주입 fallback, query 전달 경로.
- 회귀: 기존 skill injection 테스트(전부 주입 가정)가 플래그 off에서 그대로 통과하는지.
- 검증: `verify-architecture`, `verify-logging`, 격리 pytest(Windows 이벤트 루프 flakiness 회피 — CC 메모리).

### 5-2. Cross-Project (API 계약)
- 실행 API 응답 스키마 변경 **없음** → `/api-contract-sync` 불필요(추정). Skill CRUD 무변경. Design에서 최종 확인.

---

## 6. 작업 분해 (TDD: Red → Green → Refactor)

1. **(Red)** `ResolvedSkills` + `build_catalog` + merge 회귀 단위 테스트.
2. **(Green)** domain: `ResolvedSkills`, `build_catalog`, `SkillResolverInterface` 추가.
3. **(Red)** `RelevanceGatedResolver` 선택 동작 테스트(관련/무관/0개/threshold).
4. **(Green)** infra: resolver 구현(전략 1차 = 임베딩 or 휴리스틱).
5. **(Red→Green)** `_inject_attached_skills` query 인자 + resolver 호출 + fallback. 통합 테스트.
6. **(Green)** config 플래그/threshold/`MAX_ATTACHED` 상향 + `main.py` DI.
7. **(회귀)** 플래그 off 전부-주입 무회귀, on 선택-주입 동작.
8. **(Refactor/verify)** verify-architecture, verify-logging, 격리 pytest 전체.

---

## 7. 리스크 / 주의사항

| ID | 리스크 | 영향 | 대응 |
|----|--------|------|------|
| R1 | 선택기 오판으로 **필요한 스킬 누락** → 답변 품질 저하 | 中 | 0개/저신뢰 시 전부-주입 fallback(8-3). threshold 보수적 설정 + 로깅으로 선택 결과 관측. |
| R2 | `description`/`trigger`가 **비어있는 기존 스킬** → 선택 신호 부족 | 中 | 비어있으면 해당 스킬은 항상 후보 포함(보수적) 또는 name 기반 fallback. |
| R3 | LLM 분류 채택 시 **run당 호출 1회** 추가 지연/비용 | 中 | 1순위 임베딩(무비용) 검토. 캐싱. 플래그로 on/off. |
| R4 | `MAX_ATTACHED` 상향이 플래그 off 경로의 eager 주입과 만나면 **토큰 폭증** | 高 | cap 상향은 플래그 on에 **연동**. off면 기존 3 유지. |
| R5 | 40,000자 가드 silent drop 기존 문제 잔존 | 低 | 선택 주입으로 초과 가능성↓. 차기 경고 로그 추가는 비목표(후속). |
| R6 | Windows pytest 교차 실행 flakiness | 低 | 격리 실행 검증(CC 메모리). |

---

## 8. Design 단계 Open Questions

1. **선택 전략 확정** — 임베딩 vs 경량 LLM 분류 vs 하이브리드. 임베딩이면 description/trigger 임베딩 저장/캐싱 위치(메모리 캐시 vs 사전계산 컬럼)?
2. **threshold/top_k** — 관련성 임계와 최대 선택 개수 기본값. cap 상향값(3→?).
3. **0개/저신뢰 fallback 정책** — 전부 주입(품질 우선) vs 미주입(토큰 우선) vs catalog만.
4. **`MAX_ATTACHED` 설정화** — 상수 직접 변경 대신 config/policy 인자화 방식.
5. **catalog 선노출 여부** — A에서도 선택 스킬 name 카탈로그를 supervisor에 알릴지(B 대비 점진 도입).
6. **B 전환 트리거** — 어떤 지표(스킬 수, 토큰)일 때 B로 넘어갈지 기준 메모.

---

## 9. 다음 단계

```
/pdca design skill-progressive-loading
```
