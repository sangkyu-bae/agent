# excel-generator-node Design Document

> **Summary**: excel_export를 document_generator 동형의 전용 합성 노드(ExcelGenerator)로 격상 — 하이브리드 소싱(원천 코드 변환 + 비정형 LLM 구조화) → AgentAttachmentStore 저장 → 다운로드 링크 반환.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt 0.1.x
> **Author**: 배상규
> **Date**: 2026-08-24
> **Status**: Draft
> **Planning Doc**: [excel-generator-node.plan.md](../../01-plan/features/excel-generator-node.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구는 있으나 "수집 데이터 → 엑셀 → 사용자 전달" 경로가 끊겨 있어 엑셀 산출 시나리오가 실사용 불가 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — 조립 에이전트로 데이터 수집·정리 업무를 자동화하려는 사용자 |
| **RISK** | LLM 표 구조화의 행 수 상한(비정형 경로), ~~DocumentAttachmentStore의 pdf/docx 전제~~ → **해소**: AgentAttachmentStore는 확장자 불문 + AttachmentType.EXCEL 기존재 + TTL 정리 완비 |
| **SUCCESS** | E2E: 수집→엑셀 요청 시 다운로드 링크 반환 + 파일 정상 오픈. 구조화 원천은 LLM 미경유 전량 보존. 실패 시 그래프 비중단(안내 노옵). |
| **SCOPE** | 백엔드 단독: WorkflowCompiler 분기 + 전용 노드 + store 저장/다운로드 배선. 프론트·위저드 UI·서식 커스터마이징은 스코프 밖 |

---

## 1. Overview

### 1.1 Design Goals

1. **패턴 대칭**: DocumentGenerator(infrastructure) + 전용 합성 노드(compiler) 구조를 엑셀에 동형 복제 — 코드베이스 일관성 최우선.
2. **데이터 무손실**: 구조화 원천(파싱된 엑셀 dict)은 LLM 컨텍스트를 거치지 않고 코드로 전량 시트 변환.
3. **비정형 대응**: 검색 결과·대화 문맥만 있을 때는 LLM이 표를 구조화하되 행 상한을 도메인 정책으로 강제.
4. **그래프 비중단**: 모든 실패는 안내 노옵(AIMessage) — document_generator D9 동형.
5. **무회귀**: 기존 ExcelExportTool·REST 라우트·ToolFactory 경로는 동작 불변.

### 1.2 Design Principles

- 기존 검증 코드 재사용: `PandasExcelExporter`, `ExcelSheetData`, `AgentAttachmentStore`, `_split_fill_context`, 다운로드 라우트.
- domain은 순수(외부 의존 금지): 시트 계획 스키마·행 상한 정책만.
- LLM 호출 1회 원칙(document_generator D2 동형): "시트 계획" 단일 프롬프트로 하이브리드 통합.
- 과도한 추상화 금지: application 레이어 서비스·인터페이스 신설 없음 (B안 기각 사유).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | compiler에 전부 인라인 | 풀 레이어(app 서비스+인터페이스) | document_generator 동형 복제 |
| **New Files** | 0 | 7~9 | 4 (+tests) |
| **Modified Files** | 3 | 4 | 4 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (compiler 비대화, 소싱 로직 테스트 불가) | High (단, 기존 패턴보다 두꺼움) | High (기존 문서생성기와 대칭) |
| **Effort** | Low | High | Medium |
| **Risk** | Medium | Low | Low |

**Selected**: **Option C** — **Rationale**: 사용자 확정(Checkpoint 3). document_generator와 완전 동형이라 리뷰·테스트·유지보수 관성이 그대로 적용되고, "과도한 추상화 금지" 규칙과도 정합.

### 2.1 Component Diagram

```
┌──────────────────────── WorkflowCompiler.compile() ────────────────────────┐
│  worker_def.tool_id == "excel_export"                                      │
│      └─▶ _create_excel_generator_node(llm, worker_def, auth_ctx, req_id)   │
└────────────────────────────────────────────────────────────────────────────┘
                                   │ (그래프 실행 시)
                                   ▼
┌───────────────────────── excel_generator_node ─────────────────────────────┐
│ SupervisorState ──▶ 소스 수집:                                              │
│   · analysis_source[kind=raw_source].excel  (파싱된 시트 dict)              │
│   · attachments[type=excel].file_path       (analysis_source 없을 때 파싱)  │
│   · _split_fill_context(messages) → evidence_block / conversation_block    │
│                                   │                                        │
│                                   ▼                                        │
│         ExcelGenerator.generate(...)  ← infrastructure                     │
│           1. LLM 1회: 시트 계획 JSON (raw 참조 or llm 데이터)                │
│           2. 계획 실행: raw→코드 전량 복사 / llm→행 상한 적용                │
│           3. PandasExcelExporter.export() → xlsx bytes                     │
│           4. AgentAttachmentStore.save(type=EXCEL, owner_user_id)          │
│                                   │                                        │
│                                   ▼                                        │
│  AIMessage: "엑셀 생성 완료 (파일명) / 다운로드: [파일명](/api/v1/...)"      │
└────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
      GET /api/v1/document-extractor/files/{file_id}  (owner-only, 기존 라우트)
```

### 2.2 Data Flow

```
[P1] analysis_source 존재 ──▶ 원천 시트 dict → 코드 변환 (행 수 무제한, LLM 미경유)
[P2] P1 없음 + 첨부 엑셀 존재 ──▶ 기존 엑셀 파서로 파싱 → 코드 변환
[P3] 구조화 원천 없음 ──▶ evidence/conversation → LLM 표 구조화 (MAX_LLM_ROWS 상한)
[혼합] LLM 시트 계획이 raw 참조 시트 + llm 시트를 함께 담을 수 있음
       (예: "원본 전체" 시트 + "상위 10개 정리" 시트)
```

**시트 계획(Sheet Plan) 프롬프트 계약** — LLM 호출 1회:

- 입력: (a) 구조화 원천 카탈로그 — 원천별 `시트명·컬럼·행수·샘플 최대 5행`만 (전체 데이터 미노출 → 토큰 절약·절단 회피), (b) evidence_block(상한 절단), (c) conversation_block, (d) 사용자 요청 의도.
- 출력(JSON): `{"filename": "...", "sheets": [{"source": "raw:<catalog_idx>", "sheet_name": "..."} | {"source": "llm", "sheet_name": "...", "columns": [...], "rows": [[...]]}]}`
- 실행 규칙: `raw:*` 시트는 코드가 카탈로그 원천에서 전량 복사(무손실), `llm` 시트는 행 상한 초과분을 **절단**하고 `truncated=True`로 표시(실패 아님).
- 응답 전처리(0.2): LLM 응답이 ```` ```json ... ``` ```` 코드펜스로 감싸져 있으면 펜스를 벗겨낸 뒤 `json.loads` — 파싱 실패는 `ExcelGenerateError("시트 계획 JSON 파싱 실패")`.
- LLM 호출 자체의 예외(타임아웃·rate limit 등)는 `ExcelGenerateError("시트 계획 생성 오류: …")`로 래핑 (0.2, §6.1 #3).
- `raw:<idx>` 해석은 `policies.parse_raw_index(source) -> int | None` 공개 함수로 통일 (0.2).

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| excel_generator_node (compiler) | ExcelGenerator, `_split_fill_context`, SupervisorState | 소스 수집·노드 응답 |
| ExcelGenerator (infra) | PandasExcelExporter, AgentAttachmentStore, LLM, (opt) 엑셀 파서 | 계획→변환→저장 |
| ExcelGenerator | domain/excel_generator (schemas·policies) | 계획 검증·행 상한 |
| ExcelGenerator | domain/excel_export (ExcelSheetData·ExcelExportRequest) | 기존 변환 스키마 재사용 |

---

## 3. Data Model

### 3.1 신규 도메인 스키마 (`src/domain/excel_generator/schemas.py`)

```python
@dataclass(frozen=True)
class RawSourceRef:
    """구조화 원천 카탈로그 항목 — LLM에는 요약만 노출."""
    catalog_idx: int
    origin: str            # 생산 워커 id 또는 "attachment"
    sheet_name: str
    columns: list[str]
    row_count: int
    # rows 전체는 ExcelGenerator가 별도 보관 (LLM 미노출)

@dataclass(frozen=True)
class SheetPlanItem:
    source: str            # "raw:<catalog_idx>" | "llm"
    sheet_name: str
    columns: list[str] | None = None   # llm 전용
    rows: list[list] | None = None     # llm 전용

@dataclass(frozen=True)
class ExcelGenerateResult:
    file_id: str
    filename: str
    sheet_count: int
    total_rows: int
    truncated: bool        # llm 시트가 행 상한으로 잘렸는지
    used_raw_source: bool  # 무손실 경로 사용 여부
```

### 3.2 도메인 정책 (`src/domain/excel_generator/policies.py`)

```python
MAX_LLM_STRUCTURED_ROWS = 300   # llm 시트 행 상한 (Plan FR-04)
MAX_SHEETS = 10                 # 시트 수 상한 (폭주 방지)

def parse_raw_index(source: str) -> int | None:
    """"raw:<idx>" → idx. 형식이 아니면 None (0.2 명시)."""

def validate_plan(items: list[SheetPlanItem], catalog_size: int) -> list[str]:
    """계획 검증 — 위반 사유 목록 반환 (빈 리스트 = 유효).
    빈 계획, 시트 수 상한, raw 인덱스 범위, llm 시트 columns/rows 필수.
    llm 행 상한 초과는 위반이 아니라 절단 대상 (§2.2)."""
```

**시트명 정규화 정책 (0.2, 구현 위치 `ExcelGenerator._unique_sheet_name`)**: Excel 금지문자 `[]:*?/\` 제거 → 31자 절단 → 중복 시 `_2`, `_3` 접미사로 리네임. 빈 시트명은 `Sheet`로 대체.

### 3.3 도메인 예외 (`src/domain/excel_generator/exceptions.py`)

```python
class ExcelGenerateError(Exception):
    """계획 파싱 실패·계획 무효·LLM 호출 오류·변환/저장 실패 등 생성 단계 오류."""

class NoExcelDataError(ExcelGenerateError):
    """LLM 시트 계획이 비어 있음 — 정리할 데이터 없음 (0.2 명시). 노드는 §6.1 #2 안내."""
```

### 3.4 기존 재사용 (변경 없음)

| 스키마 | 위치 | 용도 |
|--------|------|------|
| `ExcelSheetData`, `ExcelExportRequest` | `src/domain/excel_export/schemas.py` | 최종 변환 입력 |
| `StoredAttachment`, `AttachmentType.EXCEL` | `src/domain/agent_attachment/value_objects.py` | 저장 결과 |
| `analysis_source` 항목 | `supervisor_state.py:53` | `{"origin", "kind": "raw_source", "excel": {sheets...}}` |

### 3.5 ExcelGenerator 생성자 옵션 (0.2)

| 파라미터 | 기본값 | 의미 |
|----------|--------|------|
| `excel_parser` | `None` | P2(첨부 엑셀 재파싱) 활성화 키. **미주입 시 P2는 조용히 비활성** — analysis_source 없고 첨부만 있으면 P3(LLM 구조화)로 진행. `main.py`는 `PandasExcelParser()` 주입 |
| `llm_input_max_chars` | `20000` | evidence/conversation 블록 절단 상한. `main.py`는 `settings.document_generator_llm_input_max_chars`를 공유 주입 (문서생성기와 동일 정책) |

DB 스키마 변경: **없음** (마이그레이션 불필요).

---

## 4. API Specification

신규 엔드포인트 **없음**. 기존 계약 재사용 + 1건 보강:

### 4.1 Endpoint List

| Method | Path | Description | Auth | 변경 |
|--------|------|-------------|------|------|
| GET | /api/v1/document-extractor/files/{file_id} | 런타임 산출 파일 다운로드 (owner-only) | Required | `_MEDIA_TYPES`에 `.xlsx` 추가만 |
| POST | /api/v1/excel-export | 기존 REST 엑셀 변환 | Required | 변경 없음 (FR-09) |

### 4.2 `_MEDIA_TYPES` 보강 (`document_extractor_router.py`)

```python
".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
```

> 미보강 시에도 octet-stream으로 다운로드는 동작하나, 브라우저/클라이언트 MIME 처리 정합성을 위해 추가.

### 4.3 노드 응답 계약 (AIMessage)

```
성공: 엑셀 「{filename}」 생성 완료 (시트 {n}개, {rows}행)
      다운로드: [{filename}](/api/v1/document-extractor/files/{file_id})
      (truncated 시) ⚠️ 일부 데이터가 행 상한({MAX_LLM_STRUCTURED_ROWS}행)으로 축약되었습니다.
실패: 엑셀 생성 실패: {사유} — 그래프는 계속 진행 (안내 노옵)
```

---

## 5. UI/UX Design

**해당 없음** — 프론트 변경 없음(Plan 확정). 다운로드 링크는 기존 마크다운 링크 렌더링으로 소비된다. §5.4 Page UI Checklist 생략.

---

## 6. Error Handling

### 6.1 실패 시나리오와 처리 (모두 안내 노옵 — 그래프 비중단, D9 동형)

| # | 시나리오 | 감지 지점 | 노드 응답 |
|---|----------|-----------|-----------|
| 1 | ExcelGenerator 미배선 (DI 누락) | 노드 진입 시 None 체크 | "엑셀 생성기가 아직 구성되지 않았습니다 (excel_generator 미배선)." |
| 2 | 소스 전무 (원천·evidence·대화 모두 빈약) + LLM이 빈 계획 반환 | 계획 실행 전 | "엑셀로 정리할 데이터를 찾지 못했습니다. 먼저 데이터를 수집하거나 첨부해주세요." |
| 3 | LLM 호출 예외(타임아웃·rate limit) 또는 계획 JSON 파싱 실패 | `_plan_sheets` try → `ExcelGenerateError` | "엑셀 생성 실패: 시트 계획 생성 오류: …" / "…: 시트 계획 JSON 파싱 실패" (재시도 없음 — Plan 확정) |
| 4 | 계획 검증 위반 (raw 인덱스 오류·상한 초과 등) | `validate_plan` | 위반 사유 포함 실패 안내. 단, llm 행 상한 초과는 **절단 + truncated 플래그**로 성공 처리 |
| 5 | 첨부 엑셀 파싱 실패 (P2) | 파서 예외 | 해당 원천 제외하고 진행, 전부 실패 시 #2로 수렴 |
| 6 | 변환/저장 실패 (exporter `RuntimeError` · store `OSError`) | `_export_and_save` try가 **store.save까지 포함** → `ExcelGenerateError` | "엑셀 생성 실패: {사유}" |

### 6.2 로깅 (LOG-001)

- 노드 시작 `excel_generator_node start`: `request_id`, `worker_id`, `analysis_source_count`, `attachment_count` (LLM 대기 중 프로세스 사망 시에도 run 흔적 확보).
- 노드 완료 `excel_generator_node done`: `request_id`, `worker_id`, `file_id`, `sheet_count`, `total_rows`, `truncated`.
- 노드 실패 `excel_generator_node generate failed`: `request_id`, `worker_id` + 스택.
- 실패는 `logger.error(..., exception=e)` — 스택 트레이스 필수. print() 금지.

---

## 7. Security Considerations

- [x] 다운로드 owner-only: 기존 라우트의 `owner_user_id != current_user.id → 403` 상속 (GB3).
- [x] file_id = uuid4 hex + 형식 검증 → path traversal 차단 (store 기존 로직).
- [x] LLM 산출 filename 새니타이즈: store가 `PurePath(filename).name`으로 경로 컴포넌트 제거 (기존). 추가로 확장자 `.xlsx` 강제.
- [x] TTL 정리: `agent_attachment_ttl_seconds` lazy purge 상속 — 디스크 누수 방지.
- [ ] LLM 계획 JSON은 신뢰 불가 입력으로 취급 — `validate_plan` 필수 통과.

---

## 8. Test Plan

> 백엔드 단독 기능 — pytest 단위/통합 테스트가 주력. Playwright L2/L3는 해당 없음(프론트 무변경).
> Do 단계 규칙: 코드 + 테스트 = 1세트 (TDD, 테스트 먼저).

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit (domain) | validate_plan, 스키마 | pytest | Do |
| Unit (infra) | ExcelGenerator — 계획 파싱·raw 복사·상한 절단·저장 | pytest (LLM/store/exporter mock 또는 실제 exporter) | Do |
| Unit (application) | excel_generator_node — 소스 수집·노옵 분기 | pytest (generator mock) | Do |
| Integration | 다운로드 라우트 xlsx 미디어타입·owner-only | pytest + TestClient | Do |
| Regression | 기존 excel_export 테스트 전체 | pytest | Check |

### 8.2 Unit/Integration Test Scenarios

| # | 대상 | 시나리오 | 기대 결과 |
|---|------|----------|-----------|
| 1 | validate_plan | raw 인덱스 범위 밖 | 위반 사유 반환 |
| 2 | validate_plan | llm 시트 rows > 상한 | 위반 감지 (generator는 절단 처리) |
| 3 | ExcelGenerator | raw 원천 1000행 + raw 계획 | xlsx에 1000행 전량 (LLM 미경유 증명 — LLM mock에 데이터 미노출 assert) |
| 4 | ExcelGenerator | llm 시트 400행 반환 | 300행 절단 + `truncated=True` |
| 5 | ExcelGenerator | LLM 비JSON 응답 | `ExcelGenerateError` |
| 6 | ExcelGenerator | 정상 생성 | store.save 호출 (type=EXCEL, owner_user_id 전달), 결과 file_id/filename |
| 7 | node | analysis_source 존재 | 카탈로그에 원천 포함되어 generate 호출 |
| 8 | node | 첨부 엑셀만 존재 | 파서 경유 카탈로그 구성 (P2) |
| 9 | node | generator 미배선 | 안내 노옵 AIMessage, 그래프 계속 |
| 10 | node | generate 예외 | 실패 안내 AIMessage, 그래프 계속 |
| 11 | node | 성공 | 다운로드 링크 포함 AIMessage + `last_worker_id`/`token_usage` 갱신 |
| 12 | router | xlsx 파일 다운로드 | 200 + spreadsheetml MIME |
| 13 | router | 타인 파일 다운로드 | 403 |
| 14 | compiler | tool_id=excel_export 워커 | 전용 노드로 컴파일 + function_node_ids 등록 |
| 15 | 회귀 | `tests/infrastructure/excel_export/*`, `tests/api/test_excel_export_router.py` | 전부 통과 (무변경) |

### 8.3 E2E (수동/Check 단계)

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 수집→엑셀 | tavily_search + excel_export 에이전트에 "OO 데이터 수집해서 엑셀로" | 응답에 다운로드 링크, GET 시 유효 xlsx |
| 2 | 첨부 재가공 | 엑셀 첨부 + "이거 정리해서 새 엑셀로" | 원본 행 수 보존 확인 |
| 3 | 실패 비중단 | 데이터 없는 상태에서 엑셀 요청 | 안내 메시지 + run 정상 종료 |

### 8.4 Seed Data Requirements

없음 (DB 미사용 기능 — store는 파일시스템, 테스트는 tmp_path fixture).

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| SheetPlanItem·RawSourceRef·ExcelGenerateResult | Domain | `src/domain/excel_generator/schemas.py` |
| MAX_LLM_STRUCTURED_ROWS·validate_plan | Domain | `src/domain/excel_generator/policies.py` |
| ExcelGenerateError | Domain | `src/domain/excel_generator/exceptions.py` |
| ExcelGenerator | Infrastructure | `src/infrastructure/excel_generator/generator.py` |
| excel_generator_node (`_create_excel_generator_node`) | Application | `src/application/agent_builder/workflow_compiler.py` |
| DI 배선 | API (composition root) | `src/api/main.py` |
| `_MEDIA_TYPES` 보강 | API | `src/api/routes/document_extractor_router.py` |

### 9.2 Dependency Rules 준수

- domain/excel_generator: 순수 (표준 라이브러리만) — LangChain·pandas·store 미참조.
- infrastructure/excel_generator: domain(excel_generator, excel_export, agent_attachment) 참조 OK. application 미참조.
- workflow_compiler(application): infrastructure 구현체를 **주입받아** 사용 (직접 생성 금지 — 기존 document_generator 파라미터와 동일하게 `excel_generator=None` 생성자 주입).

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 노드 팩토리 명명 | `_create_excel_generator_node` (document_generator 동형) |
| 생성기 클래스 | `ExcelGenerator` — `generate(...) -> ExcelGenerateResult` (DocumentGenerator 시그니처 동형) |
| 함수 길이 | 40줄 이하 — 계획 파싱/실행/저장을 private 메서드로 분리 |
| 로깅 | StructuredLogger, `exception=` 키워드 스택 트레이스 |
| 주석 | `# Design Ref: §{n}` 아키텍처 결정 지점에만 |
| 설정 | 행 상한은 도메인 정책 상수 (config 불필요 — 외부 환경 의존 아님) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/excel_generator/
│   ├── __init__.py
│   ├── schemas.py          # RawSourceRef, SheetPlanItem, ExcelGenerateResult
│   ├── policies.py         # MAX_LLM_STRUCTURED_ROWS, MAX_SHEETS, validate_plan
│   └── exceptions.py       # ExcelGenerateError, NoExcelDataError
├── infrastructure/excel_generator/
│   ├── __init__.py
│   └── generator.py        # ExcelGenerator (계획 프롬프트·실행·변환·저장)
├── application/agent_builder/
│   └── workflow_compiler.py   # [수정] 분기 + _create_excel_generator_node + DI 파라미터
└── api/
    ├── main.py                # [수정] ExcelGenerator 생성·주입
    └── routes/document_extractor_router.py  # [수정] _MEDIA_TYPES .xlsx

src/domain/agent_builder/tool_registry.py    # [수정] excel_export 설명 갱신

tests/
├── domain/excel_generator/test_policies.py
├── domain/excel_generator/test_schemas.py
├── infrastructure/excel_generator/test_generator.py
├── application/agent_builder/test_workflow_compiler_excelgen.py   # docgen 테스트 명명 규칙 준수
├── domain/agent_builder/test_tool_registry.py   # [보강] excel_export 설명 문구 회귀 (FR-10)
└── api/test_document_extractor_router.py    # [보강] xlsx 다운로드 케이스
```

### 11.2 Implementation Order

1. [ ] domain: schemas → policies → exceptions (+tests, Red→Green)
2. [ ] infrastructure: ExcelGenerator — 계획 프롬프트 → validate_plan → raw 복사/llm 절단 → PandasExcelExporter → store.save (+tests)
3. [ ] compiler: `excel_generator` 생성자 파라미터 + 분기 + `_create_excel_generator_node` (소스 수집·노옵 분기·응답 렌더) (+tests)
4. [ ] main.py DI 배선 + router `_MEDIA_TYPES` + tool_registry 설명 (+router 테스트 보강)
5. [ ] 회귀: 기존 excel_export·workflow_compiler 테스트 전체 실행

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 생성기 코어 (domain + infrastructure) | `module-1` | 스키마·정책·ExcelGenerator + 단위 테스트 | 20-30 |
| 노드 통합 (compiler + DI + API 보강) | `module-2` | 전용 노드·배선·미디어타입·레지스트리 설명 + 테스트 | 20-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1` | 20-30 |
| Session 2 | Do | `--scope module-2` | 20-30 |
| Session 3 | Check + Report | 전체 | 20-30 |

> 변경 규모가 크지 않아 한 세션에 module-1+2를 함께 진행해도 무방.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-25 | Act-1 반영 — 예외 경계 확장(LLM 호출·store IO → ExcelGenerateError), 시작 로그, `.xlsx` 강제, `NoExcelDataError`·`parse_raw_index`·시트명 정규화·코드펜스 전처리·생성자 옵션(§3.5) 명문화, §11.1 테스트 파일명 정정 | 배상규 |
| 0.1 | 2026-08-24 | Initial draft — C안(실용 균형) 확정, 시트 계획 프롬프트 계약·하이브리드 소싱 우선순위(P1 analysis_source > P2 첨부 파싱 > P3 LLM 구조화)·저장소 리스크 해소 반영 | 배상규 |
