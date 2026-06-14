# Plan: chart-context-continuity

> Created: 2026-06-10
> Phase: Plan
> Scope: `idt/` 백엔드 — 차트/분석 데이터의 멀티턴 컨텍스트 연속성 (후속 질문에서 "해당 그래프" 참조 및 분석 데이터 재사용)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | ① 차트를 생성한 뒤 후속 질문("해당 그래프에서 각 사용자마다 색깔을 넣어줘")을 하면 AI가 어떤 그래프인지 알지 못한다. 차트(`conversation_message.charts`)는 DB에 저장되지만 설계 결정 D7("표시 전용 메타, LLM 컨텍스트 미투입")에 따라 후속 턴의 LLM 컨텍스트에 전혀 포함되지 않기 때문. ② 엑셀(추후 문서) 분석 데이터는 LangGraph 워크플로우의 메모리 상태(`ExcelAnalysisState`)에만 존재하고 DB에 저장되지 않아, 응답 직후 소실된다. "해당 그래프를 원형으로 변경해줘 / 같은 데이터로 다른 그래프도 그려줘"가 원천적으로 불가능. |
| **Solution** | ① **차트 편집 의도 라우팅 + 저장된 차트 재주입**: 후속 질문이 차트 참조/편집 의도이면 세션의 최근 `charts`를 DB에서 로드해 차트 변환 전용 경로(LLM transformer)로 처리. 일반 컨텍스트에는 차트 전체가 아닌 **1줄 캡션 메타**만 투입(D7 부분 개정). ② **분석 아티팩트 영속화**: 엑셀/문서 분석 결과(데이터 스냅샷 + 분석 텍스트 + 차트)를 세션 스코프 `analysis_artifact`로 MySQL에 저장하고, 후속 질문 시 최신 아티팩트를 로드해 차트 재생성/변형에 재사용. |
| **Function UX Effect** | 사용자가 차트 생성 후 "색 바꿔줘", "원형으로 바꿔줘", "이 데이터로 다른 그래프도 그려줘" 같은 자연스러운 후속 대화가 가능해진다. 분석 결과가 세션 동안 유지되어 엑셀 재업로드 없이 연속 분석 가능. |
| **Core Value** | 단발성 차트 생성기 → **대화형 데이터 시각화 어시스턴트**로 전환. 멀티턴 컨텍스트 일관성이라는 플랫폼 핵심 가치(보수적·예측 가능한 동작) 강화. |

---

## 1. 배경 / 문제 정의

### 1-1. 시나리오 재현

```
턴1 (User):  "부서별 대출 건수에 대해 그래프 그려줘"
턴1 (AI):    텍스트 답변 + charts=[{type: bar, ...}]  ← DB 저장됨 (charts 컬럼)
턴2 (User):  "해당 그래프에서 각 사용자마다 색깔을 넣어줘"
턴2 (AI):    ??? — "어떤 그래프를 말씀하시는지 알 수 없습니다"
```

```
엑셀 분석:   엑셀 첨부 + "월별 매출 분석해줘" → 분석 텍스트 + 차트 응답
후속 질문:   "해당 그래프를 원형으로 변경하고 다른 그래프도 그려줘"
현재 결과:   분석 데이터(DataFrame dict)가 이미 소실 → 재생성 불가
```

### 1-2. 원인 (코드 근거)

**원인 A — 차트는 저장되지만 LLM에게 보이지 않는다 (의도된 설계 D7)**

| 항목 | 위치 | 내용 |
|------|------|------|
| 차트 저장 | `src/domain/conversation/entities.py:57` | `ConversationMessage.charts: Optional[list[dict]]` — assistant 메시지에 부속, MySQL JSON 컬럼 저장 |
| 설계 결정 | `entities.py:56-57` 주석 | "chat-chart-persistence D6/D7: 표시 전용 차트 메타 (**LLM 컨텍스트 미투입**)" |
| 컨텍스트 빌드 | `src/application/general_chat/use_case.py:506-510` | `AIMessage(content=msg.content)` — **content만** 투입, charts 무시 |
| 요약 | `use_case.py:457-458` | 요약에도 charts 미포함 |

→ 후속 턴의 LLM은 이전 턴에 차트가 존재했다는 사실 자체를 모른다. "해당 그래프" 해석 불가.

**원인 B — 엑셀 분석 데이터는 어디에도 저장되지 않는다**

| 항목 | 위치 | 내용 |
|------|------|------|
| 분석 상태 | `src/application/workflows/excel_analysis_workflow.py` | `ExcelAnalysisState["excel_data"/"analysis_text"/"charts"]` — LangGraph 실행 중 메모리에만 존재 |
| 결과 객체 | `src/application/use_cases/analyze_excel_use_case.py:122-152` | `AnalysisResult` 반환 후 **DB 미저장** |
| 대화 통합 | — | 엑셀 분석은 대화 메시지 시스템(`conversation_message`)과 미통합 |

→ 응답이 끝나면 원본 데이터 스냅샷·분석 텍스트·차트가 모두 소실. 후속 질문에서 재사용할 재료가 없다.

### 1-3. 관련 제약 (기존 정책)

- **대화 메모리 정책** (`docs/rule/conversation-memory.md`): 6턴 초과 시 요약 + 최근 3턴만 컨텍스트 투입. 대화 기록 Vector DB 저장 금지(MySQL만).
- **CLAUDE.md 절대 금지 항목**: "대화 메모리 정책 변경", "DB 스키마 임의 변경" → **본 기능은 사용자 명시 요청에 따른 PDCA 절차로 진행하며, D7 결정의 부분 개정과 신규 테이블 추가를 Plan/Design 문서로 명시 승인받는다.**
- CC 메모리: 차트 렌더링은 현재 General Chat 경로에만 프론트 연결됨. Excel/Supervisor 차트 렌더링은 후속 feature.

---

## 2. 개선 가능성 판단 (사용자 질문에 대한 답)

**두 가지 모두 개선 가능하다.** 단, 난이도와 단계가 다르다.

| 시나리오 | 가능 여부 | 근거 |
|----------|:--:|------|
| ① "해당 그래프에 색깔 넣어줘" (General Chat) | ✅ 가능 (난이도 中) | 차트가 이미 `conversation_message.charts`에 저장되어 있음. **재료는 있고, 꺼내 쓰는 경로만 없음.** 의도 감지 + 재주입 + 변환 경로 추가로 해결. |
| ② "원형으로 변경 + 다른 그래프도" (엑셀 분석 후) | ✅ 가능 (난이도 中上) | 분석 데이터가 현재 휘발됨. **저장소(아티팩트 영속화)부터 만들어야 함.** 데이터 스냅샷 크기 제한 정책 필요. |

---

## 3. 목표 / 비목표

### 3-1. 목표

- **G1.** General Chat에서 직전(또는 세션 내 최근) 차트를 참조하는 후속 질문 시, 저장된 차트 config를 로드해 **수정된 차트를 반환**한다. (색상 변경, 타입 변경(bar→pie), 시리즈 분리 등)
- **G2.** LLM 일반 컨텍스트에 차트 존재를 알리는 **경량 캡션 메타**(예: `[차트 생성됨: 부서별 대출 건수 막대그래프]`)를 투입해 "해당 그래프" 지시어를 해석 가능하게 한다. (full config는 미투입 — 토큰 상한 보호)
- **G3.** 엑셀(추후 문서) 분석 결과(데이터 스냅샷 + 분석 텍스트 + 차트)를 **세션 스코프로 MySQL에 영속화**한다.
- **G4.** 분석 후속 질문("원형으로 변경", "같은 데이터로 다른 그래프") 시 저장된 아티팩트를 로드해 **차트 재생성/변형**한다.
- **G5.** 기존 일반 질문(차트 무관) 경로는 회귀 없이 동작하고, 컨텍스트 토큰 증가는 턴당 캡션 1~2줄 수준으로 제한한다.
- **G6.** TDD로 진행하고 아키텍처/로깅 규칙 검증을 통과한다.

### 3-2. 비목표

- **N1.** 프론트엔드 차트 편집 UI(차트 클릭 → 편집 모드 등)는 범위 외. 백엔드는 "최근 차트" 기준으로 동작하고, 차트 ID 지정은 확장 포인트로만 설계.
- **N2.** Excel/Supervisor 차트의 프론트 렌더링 연결(별도 feature, CC 메모리 기준 후속).
- **N3.** 대용량 원본 파일 자체의 영속 저장(파일 스토리지 도입) — 스냅샷(dict 요약) 저장까지만. 원본 재파싱 경로는 확장 포인트.
- **N4.** 요약 정책(6턴/최근 3턴) 자체의 변경 — 요약 본문에 차트 캡션 1줄 포함 여부만 Design에서 결정.
- **N5.** 대화 기록의 Vector DB 저장(정책상 금지 유지).

---

## 4. 해결 방안 (옵션 비교)

### 4-1. 문제 ① — 차트 참조 연속성

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A. Full config 컨텍스트 투입** | 최근 N턴의 charts 전체(JSON)를 AIMessage에 포함 | 구현 단순, LLM이 모든 정보 보유 | 차트 데이터 포함 시 토큰 폭증. D7 전면 폐기. 요약 정책과 충돌 |
| **B. 편집 의도 라우팅 + 지연 로드 (권장)** | ⑴ 컨텍스트에는 **캡션 1줄**만 투입 ⑵ 차트 편집 의도 감지 시(라우팅 정책 확장) DB에서 최근 charts 로드 ⑶ 전용 chart transformer(LLM, `기존 config + 사용자 지시 → 새 config`)로 변환 ⑷ 새 assistant 메시지에 charts 저장 | 토큰 비용 최소(캡션만 상시). full config는 필요할 때만. D7을 "캡션 허용"으로 부분 개정만 하면 됨. 기존 `VisualizationRoutingPolicy`/`ChartBuilderInterface` 패턴 재사용 | 의도 감지 단계 추가(오분류 리스크). 구현 범위 큼 |
| **C. 프론트에서 차트 ID 전달** | 사용자가 차트를 선택하면 chart_id를 요청에 포함 | 참조 모호성 제로 | 프론트 작업 필수(비목표 N1과 충돌), 자연어 대화 흐름 깨짐 |

**권장: B.** C의 chart_id 전달은 B 설계에 선택 파라미터로 자리만 만들어 두고(확장 포인트), 미전달 시 "세션 내 최근 charts"로 폴백.

### 4-2. 문제 ② — 분석 데이터 영속화

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A. 세션 스코프 아티팩트 테이블 (권장)** | 신규 `analysis_artifact` 테이블: `id, user_id, session_id, message_id(nullable), artifact_type(excel/document), data_snapshot(JSON), analysis_text, charts(JSON), source_filename, created_at`. 분석 완료 시 저장, 후속 질문 시 세션 최신 아티팩트 로드 | 대화 메시지 모델 비침투. 스냅샷 크기 상한/보존 정책을 독립 관리 가능. 추후 문서 분석에도 동일 구조 재사용 | 신규 테이블 + 마이그레이션. 대화-아티팩트 연결 키 설계 필요 |
| **B. conversation_message 확장** | 분석 결과를 대화 메시지로 저장하고 `charts` 컬럼 재사용 + `analysis_data` 컬럼 추가 | 단일 저장소, 이력 조회 API 재사용 | 대화 엔티티가 분석 데이터로 비대해짐. 요약/컨텍스트 빌드 경로 전반에 영향(회귀 위험). Supervisor 경로는 대화 저장 자체가 별도 흐름 |
| **C. 원본 파일 참조 + 재파싱** | 첨부 파일 보관 후 후속 질문 시 재파싱 | 데이터 무손실 | 파일 스토리지 보존 정책 필요, 매 후속 질문마다 파싱 비용/지연. 분석 텍스트·차트는 별도 저장 필요(결국 A 병행) |

**권장: A.** `data_snapshot`은 크기 상한(예: 직렬화 N KB, 초과 시 행 샘플링+통계 요약으로 축약)을 Design에서 수치로 확정. C는 상한 초과 대용량 케이스의 확장 포인트로만 명시.

### 4-3. 통합 흐름 (목표 상태)

```
후속 질문 수신
  ├─ (General Chat) 컨텍스트 빌드: content + [차트 캡션 1줄]
  ├─ 의도 라우팅: chart_edit / chart_new_from_data / 일반
  │    ├─ chart_edit          → 세션 최근 charts 로드 → ChartTransformer(LLM) → 새 charts
  │    ├─ chart_new_from_data → analysis_artifact 로드 → ChartBuilder(기존) 재호출 → 새 charts
  │    └─ 일반                → 기존 경로 그대로
  └─ 응답: answer + charts → 메시지 저장(charts 부속) → WS ANSWER_COMPLETED
```

---

## 5. 구현 단계 (Phasing)

| Phase | 범위 | 산출물 |
|-------|------|--------|
| **Phase 1** | General Chat 차트 참조 연속성 (문제 ①) | ⑴ 차트 캡션 컨텍스트 투입 (D7 부분 개정) ⑵ 차트 편집 의도 감지(`VisualizationRoutingPolicy` 확장 or 신규 정책) ⑶ `ChartTransformer` 인터페이스(domain) + LLM 구현(infrastructure) ⑷ use_case 분기 + 저장 ⑸ 테스트 |
| **Phase 2** | 분석 아티팩트 영속화 (문제 ② 저장) | ⑴ `analysis_artifact` 엔티티/ORM/리포지토리/마이그레이션 ⑵ `AnalyzeExcelUseCase`·Supervisor `data_analysis_worker` 완료 시 저장 ⑶ 스냅샷 크기 상한 정책(domain policy) ⑷ 테스트 |
| **Phase 3** | 분석 후속 질문 재사용 (문제 ② 활용) | ⑴ `chart_new_from_data` 의도 → 아티팩트 로드 → 차트 생성/변형 ⑵ "원형으로 변경 + 다른 그래프도" 복합 지시 처리 ⑶ E2E 시나리오 테스트 |

> Phase 1만으로 사용자 체감 개선(시나리오 ①)이 즉시 가능하므로 독립 배포 가능 단위로 설계한다. Phase 2/3은 엑셀 분석 결과가 세션 대화와 어느 경로(Standalone `analysis_router` vs Supervisor WS)로 연결되는지 Design에서 확정 후 진행.

---

## 6. 성공 기준 (Acceptance Criteria)

- **AC1.** 차트 생성 턴 이후 "해당 그래프에서 각 사용자(시리즈)마다 색깔을 넣어줘" → 직전 차트 기반의 색상 적용된 charts가 응답에 포함된다.
- **AC2.** "막대를 원형(파이)으로 바꿔줘" → 동일 데이터의 type 변경된 charts 반환.
- **AC3.** 엑셀 분석 완료 후 같은 세션에서 "해당 그래프를 원으로 변경하고 다른 그래프도 그려줘" → 저장된 분석 데이터 기반으로 파이 차트 + 추가 차트 반환.
- **AC4.** 차트 무관 일반 질문 경로는 기존과 동일하게 동작(회귀 테스트 통과). 캡션으로 인한 턴당 컨텍스트 증가는 상한(Design에서 수치 확정, 목표 ≤ 100 token/턴) 이내.
- **AC5.** 분석 아티팩트는 세션 스코프로 격리(타 사용자/세션 접근 불가)되고 스냅샷 크기 상한을 준수한다.
- **AC6.** pytest 전체 통과(기존 사전 실패 케이스 제외), `verify-architecture`/`verify-logging` 스킬 통과.

---

## 7. 리스크 / 주의사항

| 리스크 | 영향 | 완화 |
|--------|------|------|
| **D7 설계 결정 개정** — "charts LLM 미투입"을 "캡션만 투입"으로 변경 | 기존 chat-chart-persistence 설계 문서와 불일치 | Design 문서에서 D7 개정 이력 명시(D7-rev1). 요약에는 캡션 포함 여부를 별도 결정 항목으로 분리 |
| 차트 편집 의도 오분류 | 일반 질문이 차트 경로로 빠지거나 그 반대 | 기존 `VisualizationRoutingPolicy`의 휴리스틱+LLM 분류기 2단 패턴 재사용. 모호 시 일반 경로 폴백(보수적 동작) |
| 스냅샷 크기 폭증 (대용량 엑셀) | DB 부하, 메모리 | 크기 상한 + 샘플링/통계 축약 정책. 상한 초과 시 "재업로드 안내" 폴백 |
| 신규 테이블 = DB 스키마 변경 | CLAUDE.md 금지 항목(임의 변경) 저촉 우려 | 본 Plan/Design 승인 = 명시적 스펙. `db-migration` 스킬로 Flyway 마이그레이션 생성 |
| 6턴 초과 요약 시 차트 캡션 소실 | 오래된 차트 참조 불가 | 1차 범위는 "최근 3턴 내 차트" 보장. 요약 포함 여부는 Design 결정 항목 |
| Supervisor 경로와 General Chat 경로의 차트 파이프라인 상이 | 구현 분산 | excel-chart-routing-dedup(진행 중)의 "상단 chart_router 일원화" 결과를 전제로 Design 작성 — 선행 feature 완료 후 Phase 2 착수 권장 |
| 프론트 동기화 | charts 스키마/이벤트 변화 시 | 응답 스키마(`charts: list[dict]`) 변경 없음을 원칙으로. 변경 발생 시 `/api-contract-sync` 수행 |

---

## 8. 영향 범위

**백엔드 (idt/)**
- `src/domain/conversation/` — 차트 캡션 정책(컨텍스트 투입 규칙) 추가
- `src/domain/visualization/` — `ChartTransformer` 인터페이스, 편집 의도 분류 정책
- `src/domain/analysis_artifact/`(신규) — 엔티티, 스냅샷 축약 정책, 리포지토리 인터페이스
- `src/application/general_chat/use_case.py` — 컨텍스트 빌드(캡션), 의도 분기, 변환 경로
- `src/application/use_cases/analyze_excel_use_case.py`, `src/application/agent_builder/workflow_compiler.py` — 아티팩트 저장 훅
- `src/infrastructure/persistence/` — `analysis_artifact` ORM/리포지토리/매퍼, 마이그레이션(`db/migration/`)
- `src/infrastructure/visualization/` — LLM ChartTransformer 구현

**프론트엔드 (idt_front/)** — 원칙적으로 무변경(charts 스키마 유지). Phase 3에서 분석 차트 렌더링 연결 시 별도 feature.

**문서** — `docs/rule/conversation-memory.md`에 차트 캡션 규칙 추가(D7-rev1), chat-chart-persistence 설계 문서 개정 이력.

---

## 9. 다음 단계

1. `/pdca design chart-context-continuity` — 캡션 포맷, 의도 분류 기준, `analysis_artifact` 스키마/상한 수치, ChartTransformer 프롬프트 계약 확정
2. 선행 확인: `excel-chart-routing-dedup` 진행 상태(차트 파이프라인 일원화) — Phase 2 전제 조건
3. Design 승인 후 Phase 1부터 TDD 구현
