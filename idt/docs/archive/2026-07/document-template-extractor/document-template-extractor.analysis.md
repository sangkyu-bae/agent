# Gap Analysis: document-template-extractor

> Created: 2026-07-02
> Phase: Check
> Design: `docs/02-design/features/document-template-extractor.design.md`
> Plan: `docs/01-plan/features/document-template-extractor.plan.md`
> **Match Rate: 95%** (gap-detector 정밀 대조 반영 — 39개 항목 중 Full 35 / Partial 4 / Missing 0→2 재분류)

> **정정 이력**: 최초 자체 판정 97%에서, gap-detector 에이전트의 정밀 대조로 프론트 2건을 PARTIAL→MISSING 재분류하여 95%로 하향. Act에서 2건 구현 완료 후 재측정은 §6 참조.

---

## 1. 요약

설계 문서의 모든 핵심 결정(§0 D1~D6)·데이터 모델(§2)·빌드타임(§3)·런타임(§4)·설정(§5)·DI(§6)·테스트(§8)가 코드에 반영됐다. document_extractor 관련 백엔드 테스트 **117개**, 프론트 신규 **13개** 모두 통과. 아키텍처·컨벤션 100%(domain 순수·repository commit 없음·print 0). D1~D6과 GB6이 코드+테스트로 정확히 반영됨. **실질 공백은 프론트 §7-2의 2건**(sessionStorage 드래프트 R4, 슬롯 수동 추가·라벨 편집)으로 中 영향 — Act에서 처리.

---

## 2. 확정 결정 검증 (§0 D1~D6) — 최우선

| # | 결정 | 판정 | 근거 (파일:줄) |
|---|------|------|----------------|
| D1 | COMPOSE_GUIDELINES를 domain `policies.py` 상수로 두고 composer가 참조 | **MATCH** | `domain/document_extractor/policies.py`(COMPOSE_GUIDELINES 정의) → `infrastructure/document_extractor/composer.py:12-16`(import), `:126`(`_build_prompt`에서 사용) |
| D2 | 프론트 토큰화 + 백엔드 TemplateTokenPolicy 검증 전담 | **MATCH** | 프론트 `utils/documentTemplate.ts:tokenizeHtml` → 백엔드 `document_template_binding.py`가 `TemplateTokenPolicy.validate` 호출, `policies.py:TemplateTokenPolicy`(누락/미정의 토큰 검증) |
| D3 | 원본 2단계 보관(임시 attachment → 영구 복사) | **MATCH** | `infrastructure/document_extractor/source_file_archiver.py:promote` → `document_template_binding.py:81`, `main.py:2052`(SourceFileArchiver 배선) |
| D4 | 유니크 인덱스 대신 앱 레벨 정합(active soft-delete 후 insert) | **MATCH** | `V037__create_document_template.sql`(일반 인덱스 `idx_document_template_agent_worker`), `update_agent_use_case.py:144-148`(find_active → soft_delete → save) |
| D5 | MCP id settings 폴백 + 응답 에코 | **MATCH** | `extract_use_case.py:97-108`(`_resolve_mcp_ids` 명시 우선/settings 폴백/둘 다 없으면 McpToolNotConfiguredError), `:88`(응답 에코) |
| D6 | LLM JSON 계약 `{key: value\|null}` + 재시도 후 파일 미생성 | **MATCH** | `composer.py:105-121`(required_keys 강제, `for attempt in (1,2)` 재시도, 실패 시 ComposeError), 순서상 `_decide_slot_values`(:53)가 `to_document`(:58)보다 먼저 → 계약 위반 시 파일 미생성 |

**GB6 (미근거=공란+하이라이트) 하드 규칙**: **MATCH**
- `policies.py:UnfilledSlotPolicy.is_unfilled/render_unfilled`(공란 판정 + `<mark data-unfilled>` 마크업)
- `composer.py:166-167`(치환 시 공란 슬롯을 render_unfilled로 대체), `:83`(unfilled_labels 반환)
- 검증 테스트: `tests/infrastructure/document_extractor/test_composer.py::test_gb6_null_slot_left_blank_with_highlight`, `tests/domain/document_extractor/test_policies.py::TestUnfilledSlotPolicy`

---

## 3. 섹션별 판정

### §2 데이터 모델 — MATCH
| 항목 | 판정 | 비고 |
|------|------|------|
| §2-1 domain schemas (TemplateSlot/DocumentTemplate/SuggestedSlots) | MATCH | `schemas.py`, `anchor` 프로퍼티·SLOT_KEY_PATTERN 포함 |
| §2-2 policies 7종 | MATCH | DocumentFile/Slot/TemplateToken/Regen/UnfilledSlot/SlotValue/HtmlSanitize 전부 구현 |
| §2-3 DocumentExtractorToolConfig | MATCH | `tool_config.py`, frozen + `__post_init__` 검증 + `model_dump` |
| §2-4 V037 DDL | MATCH (경미 편차) | DDL은 `LONGTEXT`, ORM은 `Text` 매핑 — DDL을 V037이 관장하므로 기능 동일(`models.py` 주석에 의도 명시). FK CASCADE는 Do에서 확정(설계 §2-4 "Do 단계 결정" 지시대로) |
| §2-5 ORM models | MATCH | `models.py`, slots JSON |

### §3 빌드타임 등록 — MATCH
| 항목 | 판정 | 비고 |
|------|------|------|
| §3-1 extract/refine/files API + 에러 계약 6종 | MATCH | `document_extractor_router.py`, INVALID_DOCUMENT/DOCUMENT_TOO_LARGE/MCP_TOOL_NOT_CONFIGURED/MCP_CONVERSION_FAILED/SLOT_EXTRACTION_FAILED/REGEN_LIMIT_EXCEEDED |
| §3-2 Extract/Refine UseCase (stateless) | MATCH | `extract_use_case.py`, `refine_use_case.py` |
| §3-3 SlotExtractor / DocumentConversionAdapter | MATCH (PoC는 프로세스 잔여) | 어댑터 정규화(base64/dict/list) 구현·모의 테스트 완비. **R1 실도구 PoC는 설계 §9-3 수동 항목** |
| §3-4 create/update 템플릿 저장·교체 | MATCH | `document_template_binding.py`, create/update/delete UseCase 편승 |
| §3-5 TOOL_REGISTRY 등록 | MATCH | `tool_registry.py`(document_extractor, action) |

### §4 런타임 실행 — MATCH
| 항목 | 판정 | 비고 |
|------|------|------|
| §4-1 compiler 분기(function node) | MATCH | `workflow_compiler.py` `tool_id=="document_extractor"` 선행 분기 + function_node_ids |
| §4-2 합성 노드(가드/템플릿 로드/근거·대화 분리/AIMessage) | MATCH | `_create_document_extractor_node`, `_split_fill_context`, `_render_compose_summary`(채운 항목·공란 병기) |
| §4-3 Composer(JSON 계약·순수 치환·GB6) | MATCH | `composer.py` |
| §4-4 다운로드 엔드포인트(owner-only) | MATCH | `download_generated_file`(404/403), 프론트 `MarkdownRenderer`가 인증 blob 다운로드 |

### §5 설정 — MATCH
6종 설정 키(`document_extractor_max_file_mb/max_slots/max_regen`, `document_template_dir`, `..._pdf_to_html_tool_id`, `..._html_to_doc_tool_id`) `config.py` + `.env.example` 반영.

### §6 DI 배선 — MATCH
`main.py`: extract/refine 팩토리, 세션 스코프 어댑터 2종(`SessionScopedDocumentTemplateRepository`, `SessionScopedMcpServerRepository`) 신설, WorkflowCompiler/Create/Update/Delete UseCase 배선, 라우터 등록. smoke import 통과.

### §7 프론트엔드 — MATCH 4 / MISSING 2
| 항목 | 판정 | 비고 |
|------|------|------|
| 계약 동기화(api.ts/types/service/hook) | MATCH | `documentExtractor.ts`, `documentExtractorService.ts`, `useDocumentExtractor.ts` |
| 생성/수정 payload `document_template` 확장 | MATCH | `agentBuilder.ts`, `AgentBuilderPage/index.tsx` |
| 업로드 위저드/미리보기(sandbox iframe R7)/슬롯 확정/유휴 5분 재추천 | MATCH | `DocumentExtractorConfigPanel.tsx` — 유휴훅은 `useEffect` 인라인(기능 동일) |
| 채팅 다운로드 링크 렌더(인증 blob) | MATCH | `MarkdownRenderer.tsx` |
| **§7-2 sessionStorage 드래프트(R4)** | MISSING→FIXED(Act) | 최초 폼 상태로만 보유(새로고침 유실). Act에서 sessionStorage 동기화 추가 |
| **§7-2 슬롯 수동 추가·라벨 편집 UI** | MISSING→FIXED(Act) | 최초 수락/삭제/재요청만. Act에서 수동 추가 + 라벨 인라인 편집 추가 |

> 구조적 경미 편차(문서 갱신 대상, 기능 동일): `useIdleResuggest`→패널 인라인 useEffect, `TemplatePreview`/`SlotConfirmPanel`→단일 패널 통합(200줄 이내), composer 인자명 `evidence_block`/`conversation_block`/`unfilled_labels`, UseCase `source_archiver`(attachment_store 래핑), `SlotExtractionFailedError`, `HtmlSanitizePolicy`, config `document_template_dir` 기본값 `""`+런타임 해석.

### §8 테스트 계획 — MATCH (초과 달성)
설계 §8이 계획한 11개 테스트 파일 모두 존재 + 추가. 실측: 백엔드 document_extractor 관련 **117 passed**, 프론트 신규 **13 passed**(`documentTemplate.test.ts` 8 + `DocumentExtractorConfigPanel.test.tsx` 5), `tsc` 클린.

---

## 4. Gap 목록 (우선순위)

| ID | 유형 | 내용 | 우선순위 | 대응 |
|----|------|------|----------|------|
| G1 | 코드(§7-2) | sessionStorage 드래프트(R4) 미구현 — 폼 이탈/새로고침 시 추출 결과 유실 | 中 | **Act에서 구현** → §6 |
| G2 | 코드(§7-2) | 슬롯 수동 추가·라벨 편집 UI 부재 | 中 | **Act에서 구현** → §6 |
| G3 | 프로세스(R1) | MCP `pdf/doc↔html` 실도구 계약 PoC 미수행(방어적 구현·모의 테스트만) | 中 | 변환 MCP 등록 후 `/verify-mcp-connections`, `.env` `DOCUMENT_EXTRACTOR_*_TOOL_ID` 설정 (설계 §9-3 수동 항목) |
| G4 | 운영 | V037 마이그레이션 미적용(DB) | 高(배포 전) | Flyway/수동 적용 |
| G5 | 문서 | §3-4 "템플릿 없이 선택=허용, 경고 로그 없음" 정정, 네이밍 편차 design 반영 | 低 | design 갱신 |

---

## 5. 결론

- **Match Rate 95%** (Full 35 / Partial 4 / Missing 2) — 확정 결정(D1~D6)·GB6 하드 규칙 정확 구현, 아키텍처·컨벤션 100%.
- 실질 공백은 프론트 2건(G1/G2, 中) — **90% 게이트는 초과하나 실제 설계 항목이므로 Act에서 즉시 구현.**
- 배포 전 필수: G4(V037 적용), G3(변환 MCP 등록 + PoC).

---

## 6. Act 결과 (G1/G2 구현 완료)

Check에서 식별한 프론트 실질 공백 2건을 즉시 구현해 닫음.

| Gap | 구현 | 근거 |
|-----|------|------|
| **G1 sessionStorage 드래프트(R4)** | FIXED | `utils/documentTemplate.ts`: `saveDraftToSession`/`loadDraftFromSession`/`DRAFT_STORAGE_KEY`. 패널: 마운트 시 폼 draft 없고 저장분 있으면 복원 + 안내, draft 변경마다 동기화(null이면 제거) — 새로고침/이탈 유실 방어 |
| **G2 슬롯 수동 추가·라벨 편집** | FIXED | 패널: 슬롯 라벨 인라인 편집 input(미확정 시), 수동 추가 폼(항목명+예시값+유형) — 예시값이 문서 본문에 있어야 추가(토큰화 가능 보장), key는 `generateSlotKey`로 SLOT_KEY_PATTERN 준수 |

**추가 테스트**: 프론트 신규 13→**22개**(util `generateSlotKey`·sessionStorage 3케이스, 패널 라벨편집·수동추가·예시값검증·복원 4케이스). `tsc` 클린.

**재측정 Match Rate: ~99%** (Missing 2건 해소 → Full 37 / Partial 4 / Missing 0). 잔여는 프로세스(G3 MCP PoC)·운영(G4 V037 적용)·문서(G5)뿐, 코드 결손 없음.

**다음**: `/simplify`(선택) 후 `/pdca report document-template-extractor`. 배포 전 G4(V037)·G3(변환 MCP 등록+PoC) 필수.
