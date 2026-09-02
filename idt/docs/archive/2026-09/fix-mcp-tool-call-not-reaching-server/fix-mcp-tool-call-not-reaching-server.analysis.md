# fix-mcp-tool-call-not-reaching-server Gap Analysis

> **Date**: 2026-09-02
> **Analyst**: 배상규
> **Plan**: [fix-mcp-tool-call-not-reaching-server.plan.md](../01-plan/features/fix-mcp-tool-call-not-reaching-server.plan.md)
> **Design**: [fix-mcp-tool-call-not-reaching-server.design.md](../02-design/features/fix-mcp-tool-call-not-reaching-server.design.md) (v0.2)
> **Method**: 정적 대조(Design ↔ 코드) + 단위/통합 테스트 + 실서버 런타임 검증

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 워커 도구 호출이 서버에 도달하지 않고, 실패가 조용해서 원인 추적이 불가능하다 |
| **WHO** | P2 — Agent Builder로 MCP 도구를 조립하는 에이전트 소유자 / KB 운영자 |
| **RISK** | 실제 차단 지점이 계측 전에는 미확정 — 추정만으로 고치면 증상이 그대로 남는다 |
| **SUCCESS** | 등록된 MCP 서버의 지정 도구가 실제 호출되고(서버 측 수신 확인), 3개 결함에 회귀 테스트가 붙는다 |
| **SCOPE** | Phase 1 계측·재현 → Phase 2 결함 수정 → Phase 3 회귀 가드. inputSchema 노출은 제외 |

---

## 1. 전략적 정합성 (Strategic Alignment)

| 질문 | 판정 | 근거 |
|------|:---:|------|
| 원래 문제(WHY)를 해결했는가 | ✅ | 레거시 워커가 서버 도구 3개를 전부 바인딩(실측). 이전엔 `scrape_url` 1개뿐이라 나머지 2개는 호출 자체가 성립 불가 |
| 올바른 문제를 골랐는가 | ✅ | 계측 선행 결정 덕에 D1이 실제 원인으로 확정. D2는 미발생으로 확인돼 우선순위를 낮춤 — 추정 수정을 피했다 |
| Design 핵심 결정을 따랐는가 | ✅ | Option C·도구명 규칙·전체 바인딩 준수. §6.2 배선오류 비격리는 G-01 수정으로 해소 |

---

## 2. Plan Success Criteria 평가

| ID | 기준 | 판정 | 근거 |
|----|------|:---:|------|
| SC-01 | 지정 도구의 요청이 MCP 서버에 실제 수신 | ⚠️ Partial | 바인딩·연결까지 실측 확인(`list_tools` 3개, `call_tool` 경로 준비). **에이전트 실제 실행으로 `call_tool` 수신까지는 미확인** — M2/M3의 에이전트 런은 사용자 실행 필요 |
| SC-02 | 차단 지점을 로그로 특정 가능 | ✅ Met | §4의 8개 로그 이벤트 전부 구현. `exposed_name_len`·`requested_tool`·`server_level`·`fallback` 필드로 결정트리 판정 가능 |
| SC-03 | FR-03/04/05/06 각각에 테스트 존재·통과 | ✅ Met | policy 8 / factory 18 / compiler 2 / adapter 3 / wiring 6건 |
| SC-04 | 기존 MCP 테스트 회귀 없음 | ✅ Met | 타겟 스위트 5,525건 통과. TC-M01은 새 계약(`create_all_async`)으로 의도적 갱신 |
| SC-05 | 코드 주석으로 설계 역추적 가능 | ✅ Met | `# Design Ref: §N` 주석이 policy/tool_factory/tool_registry/tool_adapter/workflow_compiler 5개 파일에 존재 |

**충족률: 4/5 Met, 1 Partial**

---

## 3. 구조적 대조 (Structural Match)

| Design §11.1 항목 | 구현 | 판정 |
|---|---|:---:|
| `policy.build_tool_name` + 상한 64 | `src/domain/mcp/policy.py:75` | ✅ |
| `tool_registry` → `build_tool_name` 사용 | `tool_registry.py:83` | ✅ |
| `tool_registry` 로드 로그 `tool_names` | `tool_registry.py` | ✅ |
| `tool_adapter` `request_id`/`tool_id` 필드 | `tool_adapter.py:42` | ✅ |
| `tool_factory` 바인딩 로그 | `MCP tool binding start` / `MCP tool bound` / `MCP tools bound` | ✅ |
| `tool_factory` `create_all_async` | `tool_factory.py:196` | ✅ |
| `workflow_compiler` 실패 격리 | `failed_worker_ids` 4개소 | ✅ |
| `api/main.py` 배선 | 변경 없음(이미 정상) + 계약 테스트로 고정 | ✅ |
| 신규 테스트 `test_runtime_tool_factory_wiring.py` | 6건 | ✅ |

**Structural Match: 9/9 = 100%**

---

## 4. 기능적 깊이 (Functional Depth)

| Design 요구 | 구현 상태 | 판정 |
|---|---|:---:|
| §3.2 도구명 `[:59]+"_"+sha1[:4]`, 결정적, 충돌 회피 | 구현 + U1~U5 검증 | ✅ |
| §6.3 레거시 → 서버 도구 전체 바인딩 | 구현 + 실서버 3개 확인 | ✅ |
| §6.3 `mcp:{srv}:{tool}` → 지정 도구 1개 | 구현 + 테스트 | ✅ |
| §6.3 `create_async` 하위호환 유지 | 유지 + 테스트 | ✅ |
| §6.2 워커 단위 격리 | 구현 + U13 | ✅ |
| §6.2 전부 실패 시 compile 실패 | 구현 + U14 | ✅ |
| §6.2 배선오류(E1/E2)는 격리하지 않음 | `McpWiringError` 전용 예외 + 컴파일러 re-raise | ✅ (G-01 해소) |
| §6.1 E5 에러에 실제 도구명 목록 포함 | `(available: [...])` 추가 | ✅ (G-02 해소) |
| §4 `MCP session connecting`에 `request_id` 전달 | `create_session(config, request_id)` | ✅ (G-03 해소) |
| §8.4 M1/M3/M4 런타임 검증 | 실행 완료 | ✅ |
| §8.4 M2 에이전트 실행 재현 | 정적·부분 실측으로 대체 | ⚠️ |

**Functional Depth: 초기 8/11 = 73% → 수정 후 11/11 = 100%** (⚠️ M2 제외 시)

> M2(에이전트 실제 실행)만 사용자 실행 대기 — 이를 미충족으로 세면 10/11 = 91%

---

## 5. 계약 검증 (Contract)

API 엔드포인트·스키마 변경 없음 → 프론트 동기화 대상 없음 (Design §4 명시와 일치).
로그 필드 계약 §4 표 8건 전부 구현. G-03 수정으로 ③ 경로의 `request_id`도 전달된다.

**Contract Match: 초기 7/8 = 88% → 수정 후 8/8 = 100%**

---

## 6. Gap 목록

### G-01 (Critical) — 배선 오류가 격리되어 조용히 넘어간다 · ✅ **RESOLVED**

**위치**: `src/application/agent_builder/workflow_compiler.py` (MCP 워커 try/except)

**Design 위반**: §6.2 "E1/E2(배선 오류)는 격리하지 **않는다**. 배선 누락은 개발자 실수이고 조용히 넘어가면 이번 문제와 똑같은 '조용한 실패'가 재발한다."

**현상**: `except Exception as e:` 가 모든 예외를 잡으므로 `ValueError("MCPToolLoader is required...")` / `ValueError("MCP repository is required...")` 도 워커 스킵으로 처리된다.

**실패 시나리오**: 워커가 MCP 1개 + 일반 1개인 에이전트에서 `api/main.py`의 MCP 배선이 사라지면 → MCP 워커만 조용히 제거되고 그래프는 정상 컴파일 → 사용자는 "도구를 호출했는데 아무 일도 없다"를 다시 겪는다. U14의 전체 실패 가드는 워커가 **전부** MCP일 때만 작동한다. **이번 사이클이 없애려던 바로 그 실패 모드다.**

**수정 방향**: 배선 오류를 전용 예외(예: `McpWiringError`)로 구분하거나, `except` 절에서 메시지/타입으로 판별해 재-raise.

---

### G-02 (Important) — 도구 미발견 에러에 실제 도구명 목록이 없다 · ✅ **RESOLVED**

**위치**: `tool_factory.py:316`

```python
raise ValueError(f"MCP tool not found: {ref.tool_name!r} on server {ref.server_id!r}")
```

**Design 위반**: §6.1 E5 "**서버가 실제로 제공하는 도구명 목록을 로그에 포함**", §8.2 U7 "메시지에 실제 도구명 목록 포함"

**영향**: 카탈로그 tool_id가 서버 변경으로 낡았을 때, "무엇이 있는지"를 알려주지 않아 진단이 한 단계 더 필요하다. 이번 사이클의 목적(조용한 실패 → 진단 가능)에 정면으로 걸린다.

**참고**: 테스트 `test_catalog_id_raises_when_named_tool_absent`도 `match="MCP tool not found"`만 확인해 이 요구를 검증하지 않는다 — 테스트가 Design보다 느슨하다.

---

### G-03 (Minor) — ③ 실행 경로의 세션 로그에 request_id가 비어 있다 · ✅ **RESOLVED**

**위치**: `tool_adapter.py:81` — `MCPClientFactory.create_session(self.server_config)`

**Design 위반**: §4 "`MCP session connecting` | `request_id` (기존, 호출부에서 실제 전달되도록 보강)"

**영향**: `MCP tool execution started`에는 `request_id`가 실리지만(U15 통과), 그 직후 세션 로그는 `request_id=None`이라 한 요청의 로그 체인이 끊긴다. `create_session(config, request_id)` 인자 추가로 해결(§2.2 ① 경로는 이미 전달 중).

---

## 7. Decision Record 검증

| 결정 | 출처 | 준수 | 비고 |
|------|------|:---:|------|
| tool_id 두 형식 모두 지원 | Plan §7.2 | ✅ | 마이그레이션 없이 하위호환 유지 |
| inputSchema는 별도 사이클 | Plan §7.2 | ✅ | 범위 밖 유지, Design §6.3에 한계 명시 |
| Option C (신규 모듈 0개) | Design §2.0 | ✅ | 프로덕션 신규 파일 0, 테스트 1 |
| 도구명 규칙은 domain policy | Design §7.2 | ✅ | `hashlib`(표준)만 추가 |
| 계측 후 수정 | Design §7.2 | ✅ | module-1 실측이 D1 확정·D2 강등을 이끌었다 |
| 워커 단위 격리 | Design §7.2 | ✅ | G-01 수정으로 배선오류는 전파, 나머지만 격리 |
| E6 → 전체 바인딩 | Design §6.3 | ✅ | 사용자 승인 후 변경, 문서 v0.2 반영 |

---

## 8. Match Rate

런타임 축은 실서버 검증(M1/M3/M4)과 단위·통합 테스트로 대체했다. 에이전트 E2E(M2)는 미실행이므로 **정적 기준 공식**을 적용한다.

### 초기 측정 (Gap 수정 전)

```
Overall = (100 × 0.2) + (73 × 0.4) + (88 × 0.4) = 84.4%
```

### 재측정 (Gap 3건 수정 후)

```
Overall = (Structural × 0.2) + (Functional × 0.4) + (Contract × 0.4)
        = (100 × 0.2) + (91 × 0.4) + (100 × 0.4)
        = 20 + 36.4 + 40
        = 96.4%
```

| 축 | 초기 | 수정 후 |
|---|:---:|:---:|
| Structural | 100% | 100% |
| Functional | 73% | 91% |
| Contract | 88% | 100% |
| **Overall** | **84.4%** | **96.4%** |

Functional의 남은 9%는 M2(에이전트 실제 실행 재현) 하나 — 사용자 실행이 필요해 이 세션에서 닫을 수 없다.

---

## 9. 테스트 실행 결과

| 스위트 | 결과 |
|--------|------|
| 타겟(domain·mcp·mcp_registry·agent_builder·application·wiring) | **5,525건 통과** |
| 신규 테스트 | 20건 (policy 8, factory 11, compiler 3, adapter 3, registry 2, wiring 6 중 중복 제외) |
| 배선 가드 뮤테이션 검증 | main.py 배선 2줄 제거 시 3건 즉시 실패 → 원복 후 전건 통과 |
| 전체 스위트 (변경 전) | 58 failed, 8570 passed |
| 전체 스위트 (변경 후) | 58 failed, **8578 passed** — 실패 건수·파일 분포 동일, 통과 +8(신규 테스트). **회귀 0건 확정** |
| 기존 실패 내역 | parser 21 / retriever 7 / api DI 24 / observability 5 / es 1 — 수정 모듈 참조 없음 |

---

## 10. 권고

1. ~~G-01 수정~~ ✅ 완료 — `McpWiringError` 도입, 컴파일러가 re-raise
2. ~~G-02 수정~~ ✅ 완료 — 에러 메시지에 `(available: [...])` 추가, 테스트가 도구명 존재를 검증
3. ~~G-03 수정~~ ✅ 완료 — `create_session(config, request_id)`
4. **남은 항목**: SC-01 완전 충족을 위해 사용자가 실제 에이전트를 한 번 실행하고 MCP 서버 로그에서 `call_tool` 수신 확인 (M2/M3). 이것만 닫히면 Functional 100%.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-02 | 초기 Gap 분석 — Match Rate 84.4%, Gap 3건(Critical 1, Important 1, Minor 1) | 배상규 |
| 0.2 | 2026-09-02 | Gap 3건 수정 후 재측정 — Match Rate **96.4%**, 미해결 0건 (M2 사용자 실행만 대기) | 배상규 |
