# Document Generator — Design-Implementation Gap Analysis Report

> **Feature**: doc-generator (M1 백엔드 + M2 프론트)
> **Design (SoT)**: `idt/docs/02-design/features/doc-generator.design.md` (v1.0, 2026-08-11)
> **Plan**: `idt/docs/01-plan/features/doc-generator.plan.md` (FR-01~FR-13)
> **Analyzed**: 2026-08-11
> **Analyzer**: gap-detector

---

## 1. Executive Summary

| 항목 | 결과 |
|------|------|
| **Match Rate** | **97.2%** (85.5 / 88 항목) |
| 설계 결정 (D1~D9) | 8.5 / 9 (94.4%) |
| DB 설계 (§3) | 7.0 / 8 (87.5%) |
| 백엔드 설계 (§4) | 37.5 / 38 (98.7%) |
| 프론트 설계 (§5) | 12 / 12 (100%) |
| 테스트 설계 (§6) | 8 / 8 (100%) |
| Plan FR 충족 (FR-01~13) | 12.5 / 13 (96.2%) |
| 마이그레이션 | V059 1건 (신규 테이블, 기존 스키마 무변경) |
| 초과 구현 | 9건 — **전부 additive** (기존 계약·경로 무변경) |
| Gap | 7건 (High 0 / Medium 1 / Low 6) |

**판정**: 설계와 구현이 매우 잘 일치한다. 발견된 gap은 전부 *문서 갱신* 또는 *경미한 보강* 수준이며, 기능·계약을 되돌리는 불일치는 없다. Match Rate ≥ 90% → `/pdca report doc-generator` 진행 가능.

---

## 2. 설계 결정 (D1~D9) 항목별 판정

| ID | 결정 요지 | 판정 | 구현 위치 (근거) |
|----|-----------|:----:|------------------|
| **D1** | 생성 노드는 자체 조사 루프 없음 — 상류 워커 전체 산출물+대화 소비 | ✅ | `workflow_compiler.py:899` `self._split_fill_context(state["messages"])` 재사용. 노드는 `create_agent`/ToolFactory를 전혀 경유하지 않음(`workflow_compiler.py:285-293`에서 `continue`). 근거 블록은 `_is_worker_output` 기준이라 워커 종류 무관(`:1010`) |
| **D2** | LLM 1회 + 섹션 커버리지 재시도 1회, 미달 시 경고 후 진행 | ✅ | `generator.py:122-141` — 1차 invoke → `missing` 없으면 즉시 반환, 있으면 `_retry_instruction` 부착 재호출 → `_choose_draft`(누락 적은 쪽) → 잔여 누락은 `logger.warning` 후 진행. 2회 모두 빈 응답이면 `GenerateError` |
| **D3** | V059에 source_tool_ids 없음, 조사 방향은 guidance 텍스트로만 | ✅ | `V059__create_document_generation_type.sql:10-25` 컬럼 10종에 소스 필드 없음. `DocumentSection.guidance`(`domain/document_generator/schemas.py:17`)만 존재 |
| **D4** | 출력 기본 DOCX, PDF 선택 시 한글 폰트 경고, 백엔드는 pdf\|docx 동등 수용 | ✅ | DDL `DEFAULT 'docx'`(`:17`), `schemas.py:41` `output_format: str = "docx"`, 프론트 `EMPTY_GENERATOR_DRAFT.outputFormat='docx'`(`types/documentGenerator.ts:50`) + `PDF_KOREAN_FONT_WARNING`(`:38`) 조건부 노출(`DocumentGeneratorConfigPanel.tsx:194-198`) |
| **D5** | tool_config → generator 설정 → extractor 설정 3단 폴백, 전무 시 안내 에러 | ✅ | `generator.py:201-215` `_resolve_mcp_tool_id`, 주입은 `main.py:2528-2529`. 전무 시 `McpToolNotConfiguredError` + 설정 키 안내 문구 |
| **D6** | supervisor 라우팅 가이드 — 강제 아닌 판단 기준, generator+타 워커 공존 시만 주입 | ✅ | `workflow_compiler.py:957-1002` `_render_docgen_guidance_block` (generator 없음/단독이면 `""`), `supervisor_nodes.py:189` 파라미터 + `:236` 프롬프트 삽입. "충분하면 …바로 문서생성 워커로 위임" 포함 |
| **D7** | sanitize·예외·tracer 재사용 + 신규 project `document-generator` | ✅ | `generator.py:11-12,74`, `langsmith.py:100-108` |
| **D8** | AIMessage(name=worker_id) 1건 + `last_worker_id` 갱신, 요약에 파일명·**섹션 수**·근거 사용 여부·누락 섹션 | ⚠️ | 규약 준수 ✅(`workflow_compiler.py:862-869`). 요약(`:938-955`)에 파일명·다운로드·근거 미사용 표시·누락 섹션은 있으나 **섹션 수 문구 누락** → G1 |
| **D9** | 가드 실패 = 안내 노옵 (미배선 / 유형 미등록 / soft-delete) | ✅ | `workflow_compiler.py:881-897` 3종 전부 `_reply`로 그래프 비중단. 테스트 3건 대응 |

---

## 3. Design §3 — DB(V059) 명세 대조

| # | 명세 항목 | 판정 | 근거 / 비고 |
|:--:|-----------|:----:|-------------|
| 1 | 테이블명 `document_generation_type`, PK `id` | ✅ | `V059:10,21` |
| 2 | 컬럼 10종·타입 | ⚠️ | 전부 존재. **`worker_id` VARCHAR(64) → 구현 VARCHAR(100)** — 워커 ID 실제 폭에 맞춘 상향, 구현이 우수. Design 갱신 필요 (G3) |
| 3 | 테이블 + 전 컬럼 COMMENT | ✅ | `V059:11-25`, DDL 검사 테스트 자동 포섭 (ENFORCED_FROM=54) |
| 4 | FK `ON DELETE CASCADE`, CHARSET/COLLATE 미명시, `ENGINE=InnoDB`만 | ✅ | `V059:23-25` + errno 3780 근거 주석 |
| 5 | 인덱스 | ⚠️ | 설계 단일 `(agent_id)` → 구현 **복합** `(agent_id, worker_id, status)` — `find_active_by_agent_worker` 쿼리에 정확 대응. 구현이 우수, Design 갱신 필요 (G3) |
| 6 | SQLAlchemy 모델 `comment=` 동반 | ✅ | `infrastructure/document_generator/models.py:20-52` |
| 7 | UNIQUE 미사용 + 활성 1건은 바인딩 로직 보장 | ✅ | DDL 주석 + `update_agent_use_case.py:244-252` |
| 8 | mcp 도구 id·type_id는 워커 tool_config 저장 | ✅ | `document_generation_type_binding.py:63-68` |

---

## 4. Design §4 — 백엔드 명세 대조 (요약)

38항목 중 37.5 일치 (98.7%). 전체 항목별 표는 gap-detector 원본 판정 기준:

- **도메인**(§4-2): 스키마·정책·가이드라인·tool_config·예외·도구 등록 — 전부 ✅.
  `GenerationTypePolicy` 분리는 규칙 집합 동일(SRP 개선, 초과 아님).
- **바인딩**(§4-3): build/persist/ensure + create Step 1.8/4.7 + update 교체 + delete 캐스케이드 +
  get 프리필(FR-12) + additive 스키마 — 전부 ✅.
- **런타임**(§4-4): 분기·가드·컨텍스트 분리·실패 표면화·generate 5단계·GenerateResult·
  LangSmith·supervisor 가이드 주입 조건·config 3건·DI 배선(런타임 싱글톤+빌드타임 팩토리 4곳)·
  어댑터/저장소 기존 인스턴스 공유 — 전부 ✅.
- 유일 편차: **모델 파일 경로** — Design §4-1의 `infrastructure/db/models.py`는 리포에 없는 경로(오기).
  구현은 `infrastructure/document_generator/models.py` (추출기 선례 동형) → G2.

---

## 5. Design §5 — 프론트 명세 대조

12/12 (100%). types/utils/Panel(섹션 CRUD·DOCX 기본·PDF 경고·MCP 입력·소스 안내문)/프리필/
LeftConfigPanel 배선·배지/`constants/api.ts` 무변경(신규 엔드포인트 0)/ToolPickerModal 수정 불요
(카탈로그 기동 동기화로 자동 노출, `_normalize_tool_id`가 `internal:` prefix 정규화) — 전부 ✅.

§5-3 테스트 함정: `noValidate`/`fireEvent`·`LoadingButton`은 이 패널 구조상 비해당,
MSW per-file listen은 통합 테스트에서 준수.

---

## 6. Design §6 — 테스트 설계 대조

8/8 (100%) + 설계 표 초과 3파일(repository 6건·create 5건·get 4건).

| 설계 항목 | 실제 |
|-----------|------|
| 도메인 정책 | test_policies.py 22건 + test_tool_config.py 6건 |
| 바인딩 | test_document_generation_type_binding.py 9건 + update 교체 단언 |
| 생성기 | test_generator.py 13건 (폴백 체인 3건·입력 절단·pdf 포맷 초과 커버) |
| 컴파일러 | test_workflow_compiler_docgen.py 7건 |
| supervisor 가이드 | test_supervisor_docgen_guidance.py 5건 |
| V059 DDL | test_migration_ddl_comments.py 자동 포섭 |
| 프론트 Panel | DocumentGeneratorConfigPanel.test.tsx 9건 + documentGenerator.test.ts 5건 |
| 프론트 MSW 통합 | index.test.tsx 문서생성기 describe 3건 (생성 전송/미편집 미전송/프리필→교체 왕복) |

---

## 7. Plan FR-01~FR-13 충족

12.5/13 (96.2%). FR-02~FR-13 전부 ✅.
**FR-01 ⚠**: 등록·수정(교체)·검증 실패 롤백 ✅, 단 독립 "삭제" 경로 없음 —
에이전트 삭제 캐스케이드만 존재 (G4).

NFR: 레이어 준수·DDL·TDD·상한 config화·관측 ✅. 함수 40줄 규칙만 미충족 (G5).

---

## 8. 초과 구현 (전부 additive — 회귀 리스크 0 평가)

1. `DocumentGenerationTypeRepositoryInterface` (도메인 인터페이스)
2. `GenerationTypePolicy` 분리 (SRP)
3. `DocumentGeneratorConfigModal.tsx` (추출기 모달 선례 동형)
4. `utils/documentGenerator.ts` 순수 변환 함수
5. `GeneratorSummaryBadge` (미등록 상태 가시화)
6. 도구 해제 시 드래프트 정리 2곳 (유령 payload 방지)
7. V059 복합 인덱스 (실제 쿼리 대응)
8. 테스트 3파일 추가
9. 노드 예외에 `McpToolNotConfiguredError` 명시 포착

`supervisor_nodes.py`의 `docgen_guidance_block: str = ""` 기본값이 기존 에이전트 프롬프트
무변경을 보장 (`test_empty_block_leaves_prompt_unchanged`로 고정).

---

## 9. Gap 목록 및 권고 조치

| ID | 심각도 | Gap | 위치 | 권고 조치 |
|----|:------:|-----|------|-----------|
| **G5** | **Medium** | 함수 길이 40줄 규칙 초과 — `_create_document_generator_node` 91줄(내부 노드 64줄), `_render_docgen_guidance_block` 46줄 | `workflow_compiler.py:846-1002` | (a) 가드 검사부 헬퍼 추출로 축소 또는 (b) 클로저 팩토리 패턴을 규칙 예외로 명문화 (추출기 선례 동형). 기능 영향 없음 |
| **G1** | Low | D8 요약 규약의 "섹션 수" 문구 누락 | `workflow_compiler.py:938-955` | 요약에 섹션 수 1줄 추가(권장) 또는 D8 문구 정정. `section_count`는 이미 채워짐 |
| **G2** | Low | Design §4-1 모델 경로 오기 (`infrastructure/db/models.py`는 부재 경로) | Design §4-1 | Design 갱신 — 코드가 진실 (`document_generator/models.py`) |
| **G3** | Low | V059 스펙 편차 — worker_id 64→100, 인덱스 단일→복합 | Design §3 | Design DDL 블록 갱신 (구현이 우수, 배포 영향 없음) |
| **G4** | Low | FR-01 "삭제": generator 도구 해제 후 저장해도 활성 유형 row 잔존 | `update_agent_use_case.py` | 런타임 무해(워커 부재→노드 미컴파일·프리필 None). 정합 원하면 "워커 부재+활성 유형 → soft-delete" 분기 추가 또는 FR-01 문구 정정 |
| **G6** | Low | `DocumentGeneratorToolConfig(**tool_config)` 미지 키 → `TypeError`가 except 미포함 — D9 노옵 우회 가능 | `workflow_compiler.py:903,913-918` | except 튜플에 `TypeError` 추가 (1줄) |
| **G7** | Low | 유형명 상한 불일치 — UI 100 / Pydantic 200 / 도메인 100 | `schemas.py:38` | `max_length=100` 정렬 (에러 메시지 계층만 영향) |

**High 심각도 gap 없음.**

---

## 10. 검증 제외 항목 (E2E — 이월, gap 아님)

1. **V059 실제 적용** — MySQL 마이그레이션 + FK 콜레이션 무오류 확인. **배포 전 필수.**
2. DOCX 실측 — "휴가계획서(조사 없이 대화만)" 경로: 섹션 순서·한글 정상.
3. DOCX 실측 — "시장조사 보고서(search 선행)" 경로: 근거 반영 + supervisor 위임 순서.
4. PDF 한글 폰트 깨짐 재현 (별도 트랙 doc-convert-korean-font).
5. LangSmith `document-generator` 프로젝트 run 수신.
6. 다운로드 링크 owner-only 동작.
7. 섹션 커버리지 재시도 실화(실 LLM 누락 빈도·재시도 성공률).

---

## 11. 권고 다음 단계

1. **즉시(선택, 각 1줄)**: G1 요약 문구 + G6 TypeError 포착 + G7 max_length 정렬 — 회귀 위험 0.
2. **문서 갱신(필수)**: G2·G3 — Design을 코드 기준으로 정정 (SoT: 코드가 진실).
3. **판단 필요**: G4(삭제 경로)·G5(함수 길이 규칙) — 보강 vs 규약 정정.
4. **배포 전**: V059 적용 + 변환 MCP 도구 설정 확인.
5. **Match Rate 97.2% ≥ 90%** → `/pdca report doc-generator` 진행 가능, iterate 불필요.
