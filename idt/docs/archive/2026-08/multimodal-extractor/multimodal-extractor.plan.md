# multimodal-extractor Planning Document

> **Summary**: 문서(PDF·이미지·Office)에서 그림·차트·이미지형 표·스캔 페이지를 뽑아내어, 관리자가 선택한 비전 모델로 텍스트/구조 해석을 생성해 반환하는 **모델 확장형(레지스트리) 추출 모듈**. 저장·색인은 스코프 밖(다른 모듈이 결과를 소비).
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-21
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 적재 파이프라인은 PDF를 `multimodal`로 분류(`pdf_analyzer`)까지만 하고, 그림·차트·스캔 표의 **내용은 전량 버린다** (`pymupdf4llm_parser.py:98 write_images=False`, 파서 포트는 `List[Document]`만 반환). 규정집의 흐름도·요율 차트·스캔 표가 검색 불가 → P1/P2의 "근거를 열어 확인" 시나리오(S2)에 구멍. |
| **Solution** | `domain/multimodal` 포트 + `infrastructure/multimodal` 어댑터(추출기 × 비전 모델)로 구성된 독립 모듈. 결과는 `MultimodalElement[]`(유형·페이지·위치·설명·구조화 데이터·이미지 바이트)로 인프로세스 반환. 비전 모델은 `llm_model` 레지스트리에 `supports_vision` 플래그를 더해 재사용하고, 전역 설정 테이블에서 관리자가 1개를 고른다. 미리보기 API로 결과를 육안 검증. |
| **Function/UX Effect** | 관리자: `/admin/llm-models`에서 vision 모델 등록 → 새 "멀티모달 추출" 설정 화면에서 모델·상한·언어 선택 → 미리보기로 샘플 PDF 결과 확인. 이후 저장 모듈이 연결되면 P4가 "이 차트에서 한도가 얼마?"에 답을 받는다. |
| **Core Value** | "모델은 고정, 데이터가 성장" 원칙 유지 — 특정 벤더 API에 코어를 묶지 않고 **어댑터 1개 추가 = 모델 1개 추가**. 비용·실패 가드가 내장돼 적재가 비전 모델 때문에 중단되지 않는다(건별 degraded). |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 파이프라인이 문서의 시각 정보(그림·차트·스캔 표)를 버려 RAG 근거에 구멍이 난다 |
| **WHO** | P3 관리자(모델·가드 설정), P2 KB 운영자(미리보기로 품질 확인), 간접 수혜 P1/P4(답변 근거) |
| **RISK** | 비전 호출 비용/지연 폭증 + 벤더별 이미지 입력 형식 차이로 어댑터가 누수 → 상한·필터·동시성 가드를 설정값으로 강제, 포트 계약은 AST 테스트로 고정 |
| **SUCCESS** | 실 PDF 1건에서 OpenAI·Anthropic·로컬(OpenAI 호환) 3종 어댑터 모두 `MultimodalElement[]` 반환(실 LLM 1회 이상), 건별 실패 시 나머지 정상 반환, 미리보기 API로 확인 가능, 회귀 FAILED 목록 diff 0 |
| **SCOPE** | Phase 1: 도메인 계약+PDF 추출기+비전 어댑터 3종+설정 테이블+관리자 API·화면+미리보기 API / Phase 2(후속 사이클): 저장 모듈 연동, DOCX·PPTX·단독 이미지 추출기 / 확장 포인트만: 엑셀 차트, Gemini |

---

## 1. Overview

### 1.1 Purpose

업로드 문서에 포함된 **비텍스트 정보(그림·다이어그램·차트·이미지형 표·스캔 페이지)** 를 추출하고, 관리자가 선택한 비전 LLM으로 해석해 **검색·저장 가능한 구조화 결과**로 돌려주는 모듈을 만든다. 이 모듈의 책임은 "추출 → 해석 → 반환"까지이며, 청크화·Qdrant/ES 저장은 **별도 모듈(후속 사이클)** 이 이 모듈의 출력을 소비한다.

### 1.2 Background

- 현재 고급 적재 그래프는 `analyze → route → parse → layout_analyze → table_preprocess → chunk → morph → dual_store`이며 이미지 관련 상태가 하나도 없다 (`src/infrastructure/pipeline/state/advanced_pipeline_state.py`).
- `pdf_analyzer`(아카이브 완료, Check 99%)는 페이지별 `image_count / image_area_ratio / table_count`를 이미 계산해 `multimodal` 유형을 판정한다 → **"그림이 있는가" 신호는 이미 존재**, 본 모듈은 이를 게이트로 재사용한다.
- 라우팅은 `multimodal → llamaparser`(`src/domain/pdf_routing/value_objects.py:5-10`)로 보내지만 LlamaParse 경로도 그림 내용을 뽑지 않는다.
- `docling-pdf-parser.plan.md`는 `extract_images`를 명시적으로 Out of Scope로 미뤘다(§2.2) — 본 모듈이 그 이월분이다.
- LLM 레지스트리(`LlmModel`)에 vision 지원 여부 필드가 없고, `LLMFactory`는 openai/anthropic/ollama 3종을 생성한다. LangChain image content block은 동일 객체로 동작하므로 **클라이언트 생성 경로는 재사용**하고 "어떤 모델이 vision인가"와 "이미지를 어떤 형식으로 넣는가"만 새로 정의하면 된다.
- 업로드 원본도, 이미지 저장소도 없다. 따라서 본 모듈은 바이너리를 **보관하지 않고 결과에 동봉**한다(Q7 확정).

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` — S1(P2 폐루프), S2(근거 확인), S5(원본 역추적)
- 비전: `idt/docs/architecture/growing-agent-vision.md` — 원칙 "모델은 고정, 데이터가 성장"
- 선행: `docs/archive/2026-05/pdf-analyzer/` (완료), `docs/01-plan/features/docling-pdf-parser.plan.md` (Draft, extract_images 제외)
- 위키 패턴(필수 준수): `backend/patterns/llm-output-trust-boundary.md`, `structured-output-strict-schema.md`, `degradation-vs-failure-boundary.md`, `ast-source-contract-tests.md`, `detachable-module-seam.md`, `app-lifetime-client-singleton.md`, `conventions/config-single-source-at-consumption.md`, `backend/db/mysql-fk-collation.md`
- 규칙: `docs/rules/db-session.md`, `docs/rules/logging.md`, `docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope (Phase 1 — 이번 사이클)

- [ ] **도메인 계약** `src/domain/multimodal/`: `MultimodalElement`(VO), `ElementType`(figure/chart/table_image/page_scan), `ExtractionRequest/Result`, `ImageExtractorPort`, `VisionDescriberPort`, `MultimodalSettings`(VO), 필터·상한 Policy
- [ ] **PDF 이미지 추출기** (PyMuPDF): 페이지 내장 이미지 + 이미지형 표 영역 + (ocr_heavy 문서) 페이지 전체 렌더 → 후보 `ImageCandidate[]`(페이지·bbox·바이트·픽셀 크기·면적 비율)
- [ ] **노이즈 필터 Policy**: 최소 픽셀/면적 비율 미만 제외, 동일 해시 반복 이미지(헤더 로고) 1회만, 문서당 최대 N장 상한(초과분 `skipped` 상태로 결과에 남김)
- [ ] **비전 어댑터 3종**: OpenAI(gpt-4o/4.1/5 계열), Anthropic Claude, OpenAI 호환 로컬(vLLM/Ollama — Qwen-VL 등, `base_url` 경로). 유형별 프롬프트는 코드 내장, 출력 언어(ko/en)·상세도만 설정
- [ ] **구조화 출력**: figure → 설명문, chart → 설명문 + 축/계열/수치/추세(`ChartReading`), table_image → 마크다운 표, page_scan → 페이지 텍스트. LLM 출력(Draft) ↔ 계산 필드(Result) 분리
- [ ] **실행 UseCase**: 동시 호출 수·건당 타임아웃 가드, 재시도 1회(지수 백오프), 건별 degraded(`status=failed + reason`), 전체는 성공 반환
- [ ] **모델 레지스트리 확장**: `llm_model.supports_vision` 컬럼(V064) + 엔티티/스키마/시드/관리자 CRUD 반영 + `/admin/llm-models` 화면 체크박스
- [ ] **전역 설정 테이블** `multimodal_setting`(V065, 단일 행): `vision_model_id`(소프트 참조, NULL=비활성), `max_images_per_doc`, `min_image_px`, `min_area_ratio`, `concurrency`, `timeout_sec`, `output_language`, `detail_level`, `enabled`
- [ ] **관리자 API**: `GET/PUT /api/v1/admin/multimodal/settings`, `POST /api/v1/admin/multimodal/test`(선택 모델로 샘플 이미지 1장 해석 — 연결 확인)
- [ ] **미리보기 API**: `POST /api/v1/preview/multimodal`(PDF 업로드 → 결과 JSON, 이미지는 base64 썸네일) — 기존 `preview_router.py` 선례 따름
- [ ] **관리자 화면**: `/admin/multimodal`(문서·품질 그룹, `adminNav.ts` 단일 소스) — 설정 폼 + 연결 테스트 + 미리보기 탭. 프론트 타입/서비스/훅 동기화(`/api-contract-sync`)
- [ ] **확장 포인트 고정**: 추출기는 MIME/확장자 키 레지스트리(`pdf` 외 `image/*`, `docx`, `pptx`, `xlsx` 키 예약), 비전 어댑터는 `provider` 키 레지스트리(`gemini` 키 예약, 미구현 시 명시 오류)
- [ ] **테스트**: 포트 계약 AST 테스트, strict 스키마 재귀 검사, 필터/상한 Policy 단위, 어댑터 fake + **실 LLM 1회 스모크**(3종), 마이그레이션 COMMENT 검사 통과

### 2.2 Phase 2 (후속 사이클 — 본 문서에 계약만 남김)

- 저장 모듈 연동: `MultimodalElement` → child 청크/메타데이터 변환 + Qdrant/ES 색인, 답변 출처 표기 "그림 N (p.12)"
- 추출기 추가: 단독 이미지 파일(png/jpg), DOCX/PPTX 내장 미디어
- 고급 적재 그래프에 `multimodal_node` 편입(탈착형 이음매: 팩토리 None 반환=노드 미존재, 킬스위치 기본 off)

### 2.3 Out of Scope

- 엑셀 내장 차트 렌더링(확장 키만 예약), Google Gemini 어댑터(provider 키만 예약)
- 이미지 원본의 영구 보관·조회 URL(저장 모듈 결정 사항)
- 관리자 프롬프트 템플릿 편집(언어·상세도만), KB별/업로드별 모델 오버라이드(전역 1개)
- 전송 전 이미지 리사이즈(Q8에서 미선택 — 토큰 비용 이슈 발생 시 후속 검토)
- 채팅 입력 이미지 이해(첨부 멀티모달) — 별개 기능
- Parent/Child 청크 구조 변경(금지 규칙), 기존 `PDFParserInterface` 시그니처 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | PDF 바이트에서 페이지 내장 이미지를 추출해 `ImageCandidate(page, bbox, bytes, width, height, area_ratio, sha256)`로 반환한다 | High | Pending |
| FR-02 | `pdf_analyzer`의 페이지 특성(`table_count`, `has_extractable_text`)을 받아 이미지형 표 영역과 스캔 페이지(전체 렌더)를 후보에 포함한다 (`ocr_heavy`/텍스트 없는 페이지만) | High | Pending |
| FR-03 | 노이즈 필터 Policy: `min_image_px` 미만, `min_area_ratio` 미만 제외; 동일 sha256 반복 이미지는 첫 1건만 유지; 순수 도메인 함수 | High | Pending |
| FR-04 | 문서당 `max_images_per_doc` 상한. 초과분은 호출 없이 `status=skipped, reason=limit`로 결과에 남긴다(조용한 절단 금지) | High | Pending |
| FR-05 | `VisionDescriberPort.describe(image, element_type, options) -> DescriptionDraft` 계약. 어댑터 3종(openai / anthropic / openai_compatible) 구현 | High | Pending |
| FR-06 | 유형별 코드 내장 프롬프트 4종(figure/chart/table_image/page_scan) + `output_language`(ko/en)·`detail_level`(brief/detailed) 주입 | High | Pending |
| FR-07 | 구조화 출력: chart는 `ChartReading(chart_type, axes, series[], values[], trend)`, table_image는 `markdown_table`, 공통 `description`, `keywords[]`. strict structured output 호환(자유 키 dict 금지) | High | Pending |
| FR-08 | LLM Draft 스키마와 서버 계산 필드(status, elapsed_ms, model_id, page, bbox, sha256)는 분리된 타입. 필드 집합 동등 비교 테스트 | High | Pending |
| FR-09 | 실행 가드: `concurrency` 세마포어, 건당 `timeout_sec`, 1회 재시도(지수 백오프, 429/timeout만). 실패 건은 `status=failed, reason`으로 포함, 전체 결과는 정상 반환 | High | Pending |
| FR-10 | 설정 오류(모델 미선택·비활성·API 키 없음)는 degraded가 아니라 **명시적 예외**로 전파(설정 실수 은폐 금지) | High | Pending |
| FR-11 | `llm_model`에 `supports_vision BOOLEAN` 추가(V064). 시드의 gpt-4o·claude 계열은 true. 비전 모델 선택 목록은 `is_active AND supports_vision`만 노출 | High | Pending |
| FR-12 | `multimodal_setting` 단일 행 테이블(V065). `vision_model_id`는 `llm_model.id` 소프트 참조(FK 없음, `chunking_profile.summary_llm_model_id` 선례). 시드 1행(enabled=false) | High | Pending |
| FR-13 | 관리자 API `GET/PUT /api/v1/admin/multimodal/settings` (PUT 전체 교체, 관리자 권한), 값 범위 검증은 도메인 VO `__post_init__` | High | Pending |
| FR-14 | 연결 테스트 API `POST /api/v1/admin/multimodal/test`: 내장 샘플 이미지(또는 업로드 1장) → 선택 모델 1회 호출 → 결과·지연·모델명 반환 | Medium | Pending |
| FR-15 | 미리보기 API `POST /api/v1/preview/multimodal`(multipart PDF) → `ExtractionResult` JSON(이미지는 base64 썸네일 ≤ 256px, 원본 바이트는 제외) | High | Pending |
| FR-16 | 인프로세스 포트 `MultimodalExtractionUseCase.run(file_bytes, filename, analysis: AnalysisResult | None, request_id) -> ExtractionResult` — 저장 모듈이 주입받아 호출. `ExtractionResult.elements[].image_bytes` 원본 동봉 | High | Pending |
| FR-17 | 추출기 레지스트리: 키=확장자/MIME. Phase 1은 `pdf`만 등록, 미등록 형식은 `UnsupportedFormatError`. 비전 어댑터 레지스트리: 키=`provider`, 미등록 provider는 `UnsupportedVisionProviderError` | High | Pending |
| FR-18 | 관리자 화면 `/admin/multimodal`: 설정 폼(vision 모델 드롭다운·상한·필터·동시성·타임아웃·언어·상세도·활성), 연결 테스트 버튼, 미리보기 탭(PDF 드롭 → 요소 카드 목록). `adminNav.ts` docs-quality 그룹에 추가 | High | Pending |
| FR-19 | `/admin/llm-models` 화면·폼에 `supports_vision` 체크박스, 목록 배지 | Medium | Pending |
| FR-20 | 모든 비전 호출은 `request_id` 전파 구조화 로그(provider·model·mode·elapsed·usage 토큰)를 남기고, 어댑터는 `DescribeOutcome.usage`로 토큰을 반환하며 `callbacks` 주입점을 연다. **`ai_run` 원장 영속은 Phase 2(저장 모듈, run 컨텍스트 보유)로 이월** — 기존 `UsageCallback`은 agent run 전용(RunTracker·agent_id 필수)이라 적재 경로에서 직접 사용 불가 (Act-1에서 범위 확정) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 20장 이미지 PDF, concurrency=4 기준 미리보기 전체 ≤ 90s; 추출(비전 호출 제외) ≤ 3s/50페이지 | 미리보기 API 타이밍 로그, `step_timings` |
| Cost | 문서당 호출 수 ≤ `max_images_per_doc`(기본 50); 필터로 아이콘·로고 제거율 측정 가능(skipped 사유 집계) | 결과의 `skipped/failed/succeeded` 카운트 |
| Resilience | 건별 실패율 100%여도 UseCase는 예외 없이 반환; 설정 오류만 4xx/5xx | 단위 테스트 + fake 어댑터 전건 실패 시나리오 |
| Security | 관리자 API는 admin 권한; API 키는 `api_key_env`로만 참조(DB 저장 금지); 이미지 바이트 로그 출력 금지; base64 썸네일만 외부 노출 | 라우터 인증 테스트, 로깅 검사 |
| Architecture | domain → infrastructure 참조 0; `fitz`/LangChain import는 infrastructure만 | `/verify-architecture`, AST 테스트 |
| Observability | 호출당 model·elapsed·tokens·status 구조화 로그; 예외는 스택 포함(`exception=e`) | `/verify-logging` |
| Compatibility | 기존 파서 포트·Parent/Child 구조·적재 그래프 무변경(additive only) | 회귀 FAILED 목록 diff 0 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-20 구현 + 각 FR에 대응하는 테스트 존재(`/verify-tdd`)
- [ ] 어댑터 3종 각각 **실 LLM 1회 스모크 통과** 기록(위키: "fake로만 테스트한 LLM 모듈은 미완료")
- [ ] 미리보기 API로 실 PDF(차트·그림·스캔 표 포함 샘플) 1건 결과를 관리자 화면에서 확인
- [ ] V064/V065 `tests/db/test_migration_ddl_comments.py` 통과(COMMENT 내 콤마 금지), `ops/migration-deploy-deps.md` 갱신 제안 메모
- [ ] 프론트 타입·서비스·훅·MSW 핸들러 동기화, `adminNav.test.ts` 통과
- [ ] 회귀: 백엔드 pytest·프론트 vitest의 정렬된 FAILED 목록이 baseline과 diff 0

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 ≥ 80%
- [ ] `/verify-architecture`, `/verify-logging`, lint 0 오류, `tsc -b` 성공
- [ ] strict 스키마 재귀 검사 테스트(자유 키 dict 0건) 통과
- [ ] 포트 계약 AST 테스트: UseCase가 Protocol 미선언 메서드 호출 0건, domain 내 외부 라이브러리 import 0건

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 비전 호출 비용·지연 폭증(그림 많은 문서) | High | High | 문서당 상한·최소 크기 필터·해시 중복 제거·동시성/타임아웃을 **설정값으로 강제**, skipped 사유를 결과에 남겨 관측 |
| 벤더별 이미지 입력 형식 차이(OpenAI `image_url` vs Anthropic `source.base64` vs 로컬 호환 서버의 제한)로 어댑터 경계 누수 | High | Medium | 포트는 `bytes + mime`만 주고받고 변환은 어댑터 내부; 어댑터별 contract 테스트 + 실 LLM 스모크 |
| structured output strict 모드가 로컬(vLLM/Ollama)에서 미지원 → 400/파싱 실패 | Medium | High | 어댑터별 출력 모드 전략(strict → json_mode → 텍스트 후 파싱 폴백) 명시, 폴백 사용 시 `degraded=true` 계산 필드로 표기 |
| LLM이 계산 필드(page, status, elapsed)를 오염 | Medium | Medium | Draft/Result 타입 분리 + 필드 집합 동등 비교 테스트(위키 `llm-output-trust-boundary`) |
| 스캔 페이지 전체 렌더를 비전에 넘기면 OCR 중복·비용 과다(기존 llamaparser 경로와 충돌) | Medium | Medium | page_scan은 `has_extractable_text=false` 페이지에만, 상한에 포함; Phase 1은 결과만 반환하므로 충돌은 저장 모듈에서 정책 결정 |
| 설정 오류를 degraded로 삼켜 "결과 0건"이 조용히 지속 | Medium | Medium | FR-10: 설정 오류는 예외 전파; 연결 테스트 API로 사전 검증 |
| 업로드 원본 미보관 → 미리보기와 실제 적재 결과 불일치 재현 어려움 | Low | Medium | 결과에 `sha256`·bbox·page를 남겨 동일 PDF 재업로드 시 대조 가능 |
| `llm_model` 스키마 변경이 기존 CRUD·시드·프론트 타입에 파급 | Medium | Low | additive 컬럼(default false) + optional 필드; §6 소비처 전수 검증 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `llm_model` 테이블 / `LlmModel` 엔티티 / `LlmModelModel` ORM | DB Model | `supports_vision BOOLEAN NOT NULL DEFAULT FALSE COMMENT` 추가(V064) |
| `src/infrastructure/llm_model/seed.py` | Seed | 기본 모델의 `supports_vision` 값 지정 |
| `/api/v1/llm-models` 요청/응답 스키마 | API/Schema | optional `supports_vision` 필드 추가(additive) |
| `multimodal_setting` 테이블 | DB Model (신규) | V065, 단일 행, 소프트 참조 `vision_model_id` |
| `/api/v1/admin/multimodal/*`, `/api/v1/preview/multimodal` | API (신규) | 설정 CRUD·연결 테스트·미리보기 |
| `src/api/main.py` DI | Config | 추출기/어댑터 레지스트리·UseCase 싱글턴 배선(앱 수명) |
| `src/config.py` | Config | 신규 키 없음(모든 운영값은 `multimodal_setting`에서 소비 — dead config 금지). 필요 시 `multimodal_preview_max_bytes` 1개만 검토 |
| `idt_front/src/constants/adminNav.ts`, `types/`, `services/`, `hooks/`, `pages/AdminMultimodalPage`, `pages/AdminLlmModelsPage` | Frontend | 메뉴 1건·페이지 1개 신규, LLM 모델 폼 필드 1개 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `llm_model` | CREATE/UPDATE | `src/api/routes/llm_model_router.py` POST/PATCH → UseCase → Repository | Needs verification — optional 필드 기본 false, 기존 요청 무변경 통과 |
| `llm_model` | READ | `llm_model_router.py` GET list/one; `LLMFactory.create()`; `chunking_profile.summary_llm_model_id` 해석; 에이전트 모델 선택 UI | None — 컬럼 추가만 |
| `llm_model` | DELETE(soft) | `llm_model_router.py` DELETE | None |
| `llm_model` | SEED | `src/api/main.py:649 seed_default_models()` | Needs verification — 시드 upsert 시 신규 컬럼 포함 |
| `LLMFactory` | READ | 모든 LLM 호출 경로 | None — 변경 없음, 비전 어댑터가 재사용 |
| `pdf_analyzer.AnalysisResult` | READ | `analyze_node`, `route_node` | None — 본 모듈은 읽기만(선택 입력) |
| `preview_router.py` | — | 기존 `/preview/parse` 등 | None — 라우트 추가만(와일드카드 선등록 규칙 확인) |
| `adminNav.ts` | READ | `AdminLayout`, `AdminSectionTabs`, `TopNav` | Needs verification — 개수 하드코딩 단언 없는지 테스트 확인 |
| 프론트 `LlmModel` 타입 | READ | `AdminLlmModelsPage`, 에이전트 빌더 모델 선택 | None — optional 필드 |

### 6.3 Verification

- [ ] 위 소비처 전건이 신규 컬럼/필드 추가 후 기존 테스트 통과
- [ ] 관리자 권한 외 기존 인증·인가 변경 없음
- [ ] 기존 쿼리/뮤테이션(프론트 MSW 핸들러 포함) 깨짐 없음 — FAILED 목록 diff로 증명

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | 기존 Thin DDD 백엔드 | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 모듈 경계 | 인프로세스 포트 / HTTP 전용 / 그래프 노드 직결 | **인프로세스 포트 + 미리보기 API** | 저장 모듈이 주입받아 호출(Q4). 그래프 편입은 Phase 2에서 탈착형 이음매로 |
| 비전 모델 레지스트리 | llm_model 확장 / 별도 테이블 / 코드+config | **llm_model.supports_vision + multimodal_setting** | 기존 관리 화면·가격·base_url 재사용, 선택은 소프트 참조(chunking_profile 선례) |
| 선택 단위 | 전역 1개 / KB 오버라이드 / 업로드별 | **전역 1개** | Q3. 임베딩 레지스트리와 동일 패턴, 스키마 최소 |
| 어댑터 확장 방식 | provider 키 레지스트리 / if-분기 | **키 레지스트리(dict[provider, factory])** | 어댑터 1개 추가 = 파일 1개 + 등록 1줄, 미등록은 명시 오류 |
| 클라이언트 생성 | 신규 SDK 직접 호출 / LLMFactory 재사용 | **LLMFactory 재사용 + 어댑터는 메시지 포맷만** | API 키·base_url·usage 콜백 경로 통일 |
| 이미지 바이너리 | 동봉 / 디스크 저장소 / 폐기 | **결과에 bytes 동봉**(미리보기는 썸네일 base64) | Q7. 보관 결정은 저장 모듈 |
| 실패 정책 | 건별 degraded / 전체 실패 | **건별 degraded, 설정 오류만 예외** | 위키 degradation-vs-failure-boundary |
| 프롬프트 | 코드 내장 / 관리자 편집 | **코드 내장 + 언어·상세도 설정** | Q10. strict 스키마 보호 |
| 구조화 출력 | strict / json_mode / 텍스트 파싱 | **어댑터별 전략 + 폴백 표기** | 로컬 모델 strict 미지원 대비 |
| 입력 형식 | PDF / 이미지 / Office / 엑셀 | **PDF 구현, 나머지 키 예약** | Q11. 추출기 레지스트리(확장자 키) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD — 기존 규칙)

src/domain/multimodal/
  value_objects.py      ElementType, ImageCandidate, MultimodalElement, ChartReading,
                        MultimodalSettings(__post_init__ 범위 검증), ExtractionResult
  schemas.py            DescriptionDraft(LLM 출력 전용 — strict 호환, dict 금지)
  interfaces.py         ImageExtractorPort, VisionDescriberPort, MultimodalSettingRepository
  policies.py           NoiseFilterPolicy(min_px/min_area/hash dedupe), LimitPolicy(상한→skipped)
src/application/multimodal/
  use_case.py           MultimodalExtractionUseCase.run() — 추출→필터→상한→동시 호출→Result 조립
  settings_use_case.py  Get/UpdateSettings, TestConnection
  registries.py         ExtractorRegistry(key=ext), VisionAdapterRegistry(key=provider)
src/infrastructure/multimodal/
  extractors/pdf_pymupdf_extractor.py
  vision/openai_vision_adapter.py | anthropic_vision_adapter.py | openai_compatible_vision_adapter.py
  prompts.py            유형별 4종 프롬프트 + 언어/상세도 주입
  models.py / repository.py   multimodal_setting ORM + 세션 주입 Repository(commit 금지)
src/api/routes/
  admin_multimodal_router.py  (/api/v1/admin/multimodal/settings|test)
  preview_router.py           (+ /preview/multimodal)
db/migration/
  V064__add_supports_vision_to_llm_model.sql
  V065__create_multimodal_setting.sql
idt_front/src/
  constants/adminNav.ts(+1), types/multimodal.ts, services/multimodalService.ts,
  hooks/useMultimodalSettings.ts, pages/AdminMultimodalPage/, pages/AdminLlmModelsPage(+필드)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙(함수 40줄, if 중첩 2단계, config 하드코딩 금지, DDL COMMENT 필수)
- [x] `docs/rules/` 세부 규칙(db-session, logging, testing, tool-and-mcp)
- [x] 위키 패턴 문서(§1.3)
- [x] 프론트: ESLint/Prettier/tsconfig, `idt_front/CLAUDE.md`, 컴포넌트 파일 런타임 상수 export 금지

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | exists | 모듈명 `multimodal`, 요소 유형 StrEnum value는 wire 계약(변경=프론트 파괴) | High |
| **Registry key** | missing | 추출기 키=소문자 확장자(`pdf`), 어댑터 키=`LlmModel.provider` 문자열과 동일(`openai`/`anthropic`/`ollama`/`openai_compatible`) | High |
| **Error taxonomy** | partial | `UnsupportedFormatError`, `UnsupportedVisionProviderError`, `MultimodalNotConfiguredError`(설정 오류=예외), 건별 실패는 예외 아님(`status`) | High |
| **Env vars** | exists | 신규 없음 — API 키는 `llm_model.api_key_env` 간접 참조 | Medium |
| **DDL** | exists | COMMENT 내 콤마 금지, VARCHAR 선호(ENUM 금지), FK 없는 소프트 참조 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | 모든 운영값은 `multimodal_setting` 테이블, 키는 기존 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/로컬 `EMPTY` 관례 | Server | ☐ |

### 8.4 Pipeline Integration

해당 없음(PDCA 단독 사이클). Phase 2에서 고급 적재 그래프 편입 시 `detachable-module-seam` 패턴 적용.

---

## 9. Next Steps

1. [ ] `/pdca design multimodal-extractor` — 3안(최소/클린/실용) 비교 후 계약(VO·포트·스키마)과 어댑터 출력 모드 전략, V064/V065 DDL, API 스키마 확정
2. [ ] 실 LLM 스모크용 샘플 PDF(차트·그림·스캔 표 포함) 1건 준비 — 소유자 제공 또는 합성
3. [ ] Design 시 FR 역추적 표(FR-01~20 ↔ 설계 섹션) 작성 — 위키 `intermediate-artifact-verification`
4. [ ] 저장 모듈(Phase 2) Plan은 본 문서의 `ExtractionResult` 계약을 입력으로 별도 사이클 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-21 | 초안 — 사용자 질의 3라운드(Q1~Q11) 확정 사항 반영 | 배상규 |
| 0.2 | 2026-08-21 | Act-1: FR-20 범위 확정(구조화 로그+usage 반환, ai_run 영속은 Phase 2) | 배상규 |
