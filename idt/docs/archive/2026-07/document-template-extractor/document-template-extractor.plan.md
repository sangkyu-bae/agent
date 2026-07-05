# Plan: document-template-extractor

> Created: 2026-07-01 (rev.6 — Open Questions 확정: 앵커링=A 토큰, MCP id 명시저장, 출력=원본포맷, 공란=하이라이트, 삭제=soft-delete, 원본 보관)
> Phase: Plan
> Scope: `idt/` 백엔드 + `idt_front/` 프론트 — 신규 **"문서추출기(document_extractor)" 도구**. 하나의 도구가 **두 단계**를 가진다. **(A) 빌드타임 등록 단계**: 에이전트 빌더에서 도구를 클릭하고 PDF/Word를 올리면 MCP `pdf/doc→html`로 변환하고, 이 도구가 HTML에서 **"무엇을 자동화(변수 슬롯)할지"를 뽑아** 추천 → 사용자가 확정하면 **프론트가 보유**하다가 **"에이전트 생성" 시 DB에 저장**. **이 추출/등록 부분은 `workflow_compiler`를 타지 않는다.** **(B) 런타임 실행 단계**: 에이전트를 실행(채팅)하면 **`workflow_compiler`를 타서**, DB에 저장된 **그 에이전트·그 도구 전용 템플릿**과 누적 컨텍스트(부착 리서치 도구 근거 + 대화)로 문서를 채우고 MCP `html→pdf/doc`로 **파일까지 생성**한다. **템플릿은 그 도구에서만 쓰이며 다른 에이전트와 공유되지 않는다.**

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 여신심의서 같은 정형 문서는 매번 같은 양식에 날짜·금액·신청자명만 바뀐다. 플랫폼에 MCP `pdf/doc↔html` 변환 도구는 있으나, 이를 활용해 **양식에서 자동화할 부분을 뽑아 그 에이전트에 등록**하고, **채팅으로 그 템플릿을 채워 문서를 완성**하는 경로가 없다. 무엇을 변수화할지는 사람이 확정해야 하는데(휴먼인더룹) 그 흐름도 없다. |
| **Solution** | 신규 도구 `document_extractor`, 두 단계. **(A) 빌드타임 등록(compiler 무관)**: 도구 클릭+업로드 → MCP `pdf/doc→html` → 이 도구가 HTML에서 **자동화 슬롯(값 슬롯 `{여신금액}`·`{신청일자}` + 생성 슬롯 `{소견}`)을 추출·추천** → 미리보기 확정(거절 시 재요청, 유휴 5분 재추천) → **프론트 보유** → "에이전트 생성" 시 **그 에이전트·그 도구 전용 템플릿으로 DB 저장**. **(B) 런타임 실행(compiler 경유)**: 에이전트 실행 시 `workflow_compiler`가 이 도구를 **전용 합성 노드**로 컴파일 → **지정된 템플릿 로드 + 누적 컨텍스트(리서치 근거+대화)로 채움** → MCP `html→pdf/doc`로 파일 생성. **근거 없는 슬롯은 공란**으로 남긴다(환각 금지). |
| **Function/UX Effect** | 빌더에서 "문서추출기"를 클릭→업로드하면 "이 문서에서 여신금액·신청일자를 변수로, 소견을 자동 작성 항목으로 제안합니다"가 미리보기와 함께 뜨고, 확정 후 에이전트를 생성하면 그 양식이 **그 에이전트에** 등록된다. 이후 채팅에서 "ㅇㅇ상사 여신심의서, 오늘 날짜, 여신금액 5억, oo문서 근거로 소견도"라고 하면 완성된 PDF/Word가 나온다. |
| **Core Value** | MCP 변환 도구 자산을 "양식 등록(빌드타임) + 채팅 자동 완성(런타임)"으로 연결. 등록은 compiler와 분리해 단순·안전하게, 실행은 기존 런타임 경로에 얹어 예측 가능하게. **템플릿은 그 도구 전용**이라 동작이 명확하고, **미근거 공란 규칙**으로 신뢰성을 지킨다. |

### 관심사 분리 (rev.5)

| 구성요소 | 위치 | 근거 |
|---------|------|------|
| **① 실행 로직** — 변환·슬롯 추출·합성·파일 생성 | **Tool** (`document_extractor`, `TOOL_REGISTRY`의 공통 도구 — 어느 에이전트나 선택 가능) | 실행 능력은 Tool만 가능(skill은 instruction 주입 전용, `script_content` "저장 전용"이라 실행 불가). |
| **② 템플릿 자산** — HTML 골격 + 슬롯 구조 | **`document_template` 전용 테이블, `(agent_id, worker_id)` 종속** | 그 에이전트의 그 도구에서만 사용. **공유/fork/visibility 없음.** 도구 호출 시 지정된 템플릿만 사용. |
| **③ 작성/근거 지침** — 소견 규칙, "근거에만 기반" | **합성 노드 프롬프트 + 하드 규칙(GB6)** | 도구/양식과 밀착된 규칙이라 합성 프롬프트에 포함. (여러 에이전트가 공유할 범용 지침이 생기면 그때 Skill로 분리 — 지금은 불필요.) |

---

## 1. 배경 / 문제 정의

### 1-1. 현재 자산과 공백
- **MCP 변환 도구 보유**: MCP 레지스트리에 `pdf/doc→html`, `html→pdf/doc` 도구가 등록되어 있고, `mcp_{id}` + `MCPToolLoader.load_by_tool_id()`로 특정 MCP 도구를 호출할 수 있다 (`src/infrastructure/mcp_registry/mcp_tool_loader.py`, `src/infrastructure/agent_builder/tool_factory.py:119-146`).
- **도구 목록 노출**: 빌더 도구는 `TOOL_REGISTRY`(domain)에 등록되어 `GET /agents/tools`로 노출 (`src/domain/agent_builder/tool_registry.py`).
- **런타임 컴파일**: 실행 시 `workflow_compiler`가 각 워커를 노드로 컴파일한다. `category="action"`은 `create_react_agent(llm, tools=[tool])`, `search`/`analysis`는 전용 노드 (`src/application/agent_builder/workflow_compiler.py`).
- **파일 업로드 패턴 존재**: `agent_attachment_router`가 `UploadFile` 멀티파트 + 임시 저장(현재 xlsx 전용) (`src/api/routes/agent_attachment_router.py`, `src/infrastructure/agent_attachment/store.py`).
- **에이전트 생성 시 도구 저장**: `create_agent_use_case`가 `tool_ids`/`tool_configs`를 받아 `WorkerDefinition(tool_id, tool_config)`로 `agent_tool` 저장 (`src/application/agent_builder/create_agent_use_case.py`).
- **공백**: (1) 업로드 문서에서 자동화 슬롯을 뽑아 확정하는 도구 없음. (2) 확정 템플릿을 에이전트 생성 시 저장하는 경로 없음. (3) 실행 시 저장 템플릿으로 문서를 채워 파일 생성하는 런타임 워커 없음.

### 1-2. 확정된 아키텍처 방향 (사용자 결정 — rev.5)
1. **`document_extractor`는 "도구"** 다(에이전트 아님). 하나의 도구가 **빌드타임 등록**과 **런타임 실행** 두 단계를 가진다.
2. **빌드타임 등록(= "어떤 문서를 자동화시킬지 뽑아 DB에 등록")은 `workflow_compiler`를 타지 않는다.** 별도 추출/등록 경로.
3. **런타임 실행(= 에이전트 채팅)은 `workflow_compiler`를 탄다.** 저장 템플릿으로 문서를 채우고 파일 생성. **런타임 워커 = 전용 합성 노드**(확정).
4. 빌드타임: 클릭+업로드 → MCP 변환 → 슬롯 추출·추천 → 확정 → **프론트 보유** → "에이전트 생성" 시 **DB 저장**.
5. **템플릿은 그 에이전트의 그 도구 전용**(확정). `document_template` 테이블에 `(agent_id, worker_id)`로 종속 저장. **공유/fork/visibility 없음.** 현재 **도구당 템플릿 1개**(추후 복수 여지). 도구 호출 시 **지정된 템플릿만** 사용.
6. **미근거 = 공란**(확정, 하드 규칙 GB6). 근거 없는 슬롯은 채우지 않고 공란 + **하이라이트**(사람이 처리). 환각/추정 금지.
7. (유지) 유휴 5분 시 **추천 재생성**. 채팅 산출물은 **HTML→PDF/Word 파일**. 채움 소스는 **발화 + 부착 리서치 도구 근거 + 대화(누적 컨텍스트)**.
8. **슬롯 치환 = A(플레이스홀더 토큰)** 확정. 확정 시점에 샘플값을 `{{key}}` 토큰으로 치환해 `html_skeleton` 저장 → 런타임은 단순 문자열 치환(재현성 100%).
9. **MCP 변환 도구 id = `DocumentExtractorToolConfig`에 명시 저장**(pdf→html, html→pdf 각각). 내부 도구는 config, 변환은 MCP만 꽂아 사용.
10. **출력 포맷 = 원본 따름**: PDF 업로드→PDF 출력, Word 업로드→Word 출력.
11. **삭제 정합 = soft-delete**. **원본 파일 = 보관**(`source_file_ref`).

---

## 2. 목표 / 비목표

### 2-1. 목표 — (A) 빌드타임 등록 (compiler 무관)
- **GA1.** `TOOL_REGISTRY`에 `document_extractor`(`category="action"`) 추가, `GET /agents/tools` 노출.
- **GA2.** 추출 API(별도 경로): 업로드 → MCP `pdf/doc→html` → **HTML에서 자동화 슬롯 추출(LLM)** → 미리보기(HTML + 추천 슬롯) 반환. PDF/Word 검증. **`workflow_compiler` 미경유.**
- **GA3.** 휴먼인더룹 확정: 미리보기 → 확정 또는 재요청(refine) 재추천. 유휴 5분 재생성(상한·로깅).
- **GA4.** **프론트 보유 → 에이전트 생성 시 저장**: 확정 템플릿(HTML 골격 + 슬롯 정의 + 원본 참조)을 생성 payload에 실어 `create_agent`(및 `update_agent`)에서 **`document_template`으로 저장 + `(agent_id, worker_id)` 종속 연결**. 동일 세션 트랜잭션.

### 2-2. 목표 — (B) 런타임 실행 (compiler 경유)
- **GB1.** 실행 시 `workflow_compiler`가 `document_extractor` 워커를 **전용 합성 노드**로 컴파일. 노드는 **그 `(agent, worker)`에 지정된 템플릿을 로드**.
- **GB2.** 노드가 **누적 컨텍스트(대화 + 상류 리서치 도구/워커 산출물) 전체**를 받아 값 슬롯(사실)·생성 슬롯(소견 등 서술)을 채움.
- **GB3.** 채운 HTML → MCP `html→pdf/doc` → 파일 생성 → attachment 저장 → 다운로드 참조 반환.
- **GB4.** `flow_hint`로 "리서치(근거 수집) → 문서 합성" 순서 유도. 한 에이전트가 리서치 도구 + 문서추출기 병행 가능.
- **GB5.** 작성/근거 지침(소견 규칙·근거 제약)은 **합성 노드 프롬프트에 포함**. 도구/양식과 밀착된 규칙이므로 별도 Skill 분리는 현재 불필요.
- **GB6. (신뢰성 하드 규칙) 미근거 = 공란.** 근거가 없는 슬롯은 **절대 채우지 않고 공란으로 둔다**(값·생성 슬롯 공통). 환각/추정 금지. 공란 슬롯은 산출물에 **하이라이트**로 표시해 사람이 채우도록 남긴다. 재질문은 선택적 보조일 뿐, 기본 동작은 공란.

### 2-3. 공통 목표
- **G5.** Cross-Project: 프론트 업로드 위저드 + 미리보기/확정 UI + 타입/서비스/훅 동기화(`/api-contract-sync`).
- **G6.** TDD + `verify-architecture`/`verify-logging`/`verify-mcp-connections`. Windows 격리 pytest.

### 2-4. 비목표
- **N1.** LangGraph interrupt/checkpointer 도입(빌드타임 HITL은 프론트 보유 + stateless 추출로 처리).
- **N2.** **템플릿 공유/재사용(다른 에이전트가 선택·fork)** — 명시적 제외. 템플릿은 그 도구 전용.
- **N3.** 도구당 다중 템플릿(현재 1개). 추후 확장 여지만.
- **N4.** MCP 변환 도구 자체 구현/수정(소비만). 스캔 이미지 OCR, 금액 한글 변환 등 도메인 후처리.
- **N5.** 빌드타임 추출을 `workflow_compiler`로 실행(명시적 제외 — 확정).

---

## 3. 해결 방안

### 3-1. 전체 흐름 (두 단계)

```
[(A) 빌드타임 등록 — workflow_compiler 무관]
 프론트: 도구 목록에서 "문서추출기" 클릭 → 업로드 화면
   └ POST /document-extractor/extract   (PDF/Word 업로드)
        1) 파일 임시 저장(store)
        2) MCP pdf/doc→html → HTML 확보
        3) 이 도구의 핵심 역할: HTML 분석 LLM → 자동화 슬롯 추출·추천
             · 값(value) 슬롯:     {여신금액} {신청일자} {신청자명} …
             · 생성(generated) 슬롯: {소견} {요약} …
        4) 반환 { html, suggested_slots }   (stateless — 서버 영속 상태 없음)
   └ (거절/보강) POST /document-extractor/refine { html, instruction, prev_slots } → 재추천
   └ (유휴 5분) 프론트 미확정 방치 → extract/refine 재호출로 추천 재생성
 ▼ 확정  → 프론트가 { html_skeleton, slots, source_ref }를 폼 상태로 보유(아직 저장 안 함)
 ▼ "에이전트 생성" → POST /agents  payload.tool_configs["document_extractor"] = 확정 템플릿
        → create_agent_use_case가 document_template을 (agent_id, worker_id) 종속으로 저장 + 도구 연결

[(B) 런타임 실행 — workflow_compiler 경유]
 사용자 채팅: "ㅇㅇ상사 여신심의서, 오늘 날짜, 여신금액 5억, oo문서 근거로 소견도"
   └ workflow_compiler가 그래프 컴파일 (기존 경로)
        supervisor → [필요 시] worker(internal_document_search / tavily / analysis) # 근거 수집
                   → worker(document_extractor)  = 전용 합성 노드                     # 문서 합성
   └ document_extractor 합성 노드:
        1) DB에서 이 (agent, worker)에 지정된 DocumentTemplate 로드 (그 도구 전용)
        2) fill-context = 대화 + 상류 워커 산출물(누적 state) 전체
        3) LLM 합성: 토큰화 템플릿(`{{key}}`) + 슬롯 정의 + fill-context + 작성/근거 지침
             · value 슬롯 → 사실 값(발화/툴 데이터)으로 토큰 치환
             · generated 슬롯 → 근거 기반 서술(소견 등)으로 토큰 치환
             · 근거 없는 슬롯 → 공란(GB6, 추정/작문 금지) + **하이라이트**(사람이 채움)
        4) 치환된 HTML → MCP html→pdf/doc(**원본 포맷 따름**) → 파일 생성 → attachment 저장 → 다운로드 참조 반환
```

### 3-2. 왜 등록/실행을 분리하나
- **등록(A)** 은 사람이 확정하는 빌드타임 준비 작업이라 그래프 실행과 무관 → `workflow_compiler`를 탈 이유가 없고, **stateless 추출 + 프론트 보유 + 생성 시 저장**으로 단순화(무거운 서버 세션·즉시 승인 API 불필요).
- **실행(B)** 은 실제 에이전트 대화이므로 기존 런타임 경로(`workflow_compiler`)에 자연히 얹는다 → 리서치 도구가 모은 근거를 누적 컨텍스트로 함께 소비 가능.

### 3-3. 런타임 워커 = 전용 합성 노드 (확정)
상류 리서치 산출물이 누적 `state.messages`에 있으므로, 문서추출기 노드는 그 누적 상태를 읽는다. `search`/`analysis` 노드를 추가하는 기존 컴파일러 패턴과 동일하게, `document_extractor`를 **`state.messages`(대화+상류 산출물)를 읽는 커스텀 노드**로 컴파일한다: 지정 템플릿 로드 → 합성 LLM 1회 → 채운 HTML → MCP 변환. (단일 툴 `create_react_agent`는 상류 전체 접근이 불확실해 채택 안 함.)

### 3-4. 빌드타임 추출 stateless 근거 (A)
- 확정 전까지 서버 영속 상태가 없어도 된다(프론트가 HTML+슬롯 보유). → extract/refine은 요청/응답. 5분 재생성 = 프론트 유휴 감지 후 재호출(백엔드는 `MAX_REGEN` 상한·로깅).
- 저장은 **에이전트 생성 트랜잭션에 편승** → 도구-템플릿 연결 정합.

---

## 4. 목표 아키텍처 (DDD 레이어 배치)

> CLAUDE.md Thin DDD 준수. **(A) 등록은 compiler 무관 / (B) 실행은 compiler 경유.** 템플릿은 그 도구 전용.

| 레이어 | 추가/변경 | 단계 | 내용 |
|--------|-----------|------|------|
| **domain** | `domain/agent_builder/tool_registry.py` (변경) | A/B | `document_extractor` → `ToolMeta(category="action", requires_env=[])` 추가. |
| **domain** | `domain/document_extractor/schemas.py` (신규) | A/B | `DocumentTemplate`(id, **agent_id, worker_id**, name, **html_skeleton = `{{key}}` 토큰화된 HTML(방식 A)**, slots, **source_file_ref(원본 보관)**, **status(soft-delete)**, created_at, updated_at) — **그 도구 전용, 공유 컬럼 없음**. `TemplateSlot`(key, label, description, slot_type: value\|generated, fill_hint, sample_value, **anchor=`{{key}}` 토큰명**), `SuggestedSlots`(추출 DTO). |
| **domain** | `domain/document_extractor/policies.py` (신규) | A/B | 파일 검증(PDF/Word 확장자·크기), 슬롯 규칙(최대 개수·key 유효성), `MAX_REGEN`, **미근거 공란 판정(GB6)** 순수 규칙. |
| **domain** | `domain/document_extractor/tool_config.py` (신규) | A/B | `DocumentExtractorToolConfig`(template_id, **mcp_pdf_to_html_tool_id, mcp_html_to_pdf_tool_id — 명시 저장**, **output_format = 원본 업로드 포맷 따름(pdf→pdf/word→word)**). RAG의 `RagToolConfig` 패턴. |
| **application** | `application/document_extractor/{extract_use_case.py, refine_use_case.py, schemas.py}` (신규) | A | 업로드→MCP `pdf/doc→html`→LLM 슬롯 추출(stateless), refine 재추천(상한). **compiler 무관.** |
| **application** | `application/agent_builder/create_agent_use_case.py` (+update) (변경) | A | 생성 payload의 `document_extractor` 설정에 확정 템플릿 있으면 `DocumentTemplate`을 `(agent_id, worker_id)` 종속 저장 + `tool_config.template_id` 연결(동일 세션 트랜잭션). |
| **application** | `application/agent_builder/workflow_compiler.py` (변경) | B | 실행 시 `document_extractor` 워커를 **전용 합성 노드**로 컴파일: 지정 템플릿 로드 + 누적 컨텍스트 합성(작성 지침·GB6 포함) + MCP `html→pdf/doc`. `flow_hint`로 "리서치→합성" 유도. |
| **infrastructure** | `infrastructure/document_extractor/slot_extractor.py` (신규) | A | HTML→자동화 슬롯 추출 LLM(`llm_factory`). |
| **infrastructure** | `infrastructure/document_extractor/composer.py` (신규) | B | (지정 템플릿 + 슬롯 + 누적 컨텍스트 + 지침) → LLM 합성(GB6 공란 규칙) → 채운 HTML → MCP `html→pdf/doc` → attachment 저장. |
| **infrastructure** | `infrastructure/document_extractor/document_conversion_adapter.py` (신규) | A/B | MCP `pdf/doc→html`(A), `html→pdf/doc`(B) 호출 래퍼(`MCPToolLoader.load_by_tool_id`). |
| **infrastructure** | `infrastructure/document_extractor/document_template_repository.py` + `models.py` (신규) | A/B | `document_template` MySQL 저장(A)/조회(B). `(agent_id, worker_id)` 유니크 인덱스. |
| **infrastructure** | `infrastructure/agent_attachment/` (확장) | A/B | 업로드 정책 PDF/Word 확장(A), 산출 파일 저장/다운로드(B). |
| **interfaces/api** | `api/routes/document_extractor_router.py` (신규) | A | `POST /document-extractor/extract`, `POST /document-extractor/refine`. `api/main.py` DI. 저장은 기존 `POST /agents` 재사용. |
| **DB** | `db/migration/` (신규) | A/B | `document_template` 테이블(`agent_id, worker_id` FK+유니크, html_skeleton, slots JSON, source_file_ref). `/db-migration` 스킬로 DDL 추출. |
| **frontend** | `idt_front/` (신규/변경) | A | 도구 선택 시 업로드 위저드, HTML 미리보기+슬롯 하이라이트, 확정/재요청, **확정 결과 폼 보유**, 유휴 5분 재추천, 생성 payload에 템플릿 포함. `src/types`·`src/services`·`src/hooks`·`src/constants/api.ts` 동기화. |

### 4-1. 하위호환 / 안전 가드
- 신규 도구·라우터·테이블·합성 노드는 **추가만(additive)**. 기존 워커 컴파일/실행 무회귀.
- MCP 변환 도구 미등록/연결 실패 시: (A) 추출 API·(B) 합성 노드가 명확한 에러(어떤 MCP 도구 필요/누락) 반환. (CC 메모리: `MCP 'Session terminated' = 404`, 빈 api_key 누락 진단 힌트 재사용.)
- LLM 추출/합성 실패·빈 결과: (A) 슬롯 0개 → 수동 지정 가능. (B) **근거 없는 슬롯은 공란(GB6)** — 전면 실패 아님.
- 템플릿 없이 도구만 선택 후 실행: 로드할 템플릿 없음 → 합성 노드가 안내/노옵.
- 에이전트 삭제/도구 제거 시: 종속 `document_template`은 **soft-delete**(status='deleted'). **원본 파일은 보관**(`source_file_ref`).

---

## 5. 영향 범위 (Affected Files)

**백엔드 (idt/) — 신규**
- `src/domain/document_extractor/{schemas.py, policies.py, tool_config.py}`
- `src/application/document_extractor/{extract_use_case.py, refine_use_case.py, schemas.py}`
- `src/infrastructure/document_extractor/{slot_extractor.py, composer.py, document_conversion_adapter.py, document_template_repository.py, models.py}`
- `src/api/routes/document_extractor_router.py`
- `db/migration/V0xx__create_document_template.sql`

**백엔드 (idt/) — 변경**
- `src/domain/agent_builder/tool_registry.py` — `document_extractor` 엔트리.
- `src/application/agent_builder/create_agent_use_case.py`(+`update_agent_use_case.py`) — (A) 확정 템플릿 `(agent_id, worker_id)` 저장·연결.
- `src/application/agent_builder/workflow_compiler.py` — (B) 합성 노드 컴파일.
- `src/api/main.py` — 라우터/유스케이스 DI.
- `src/config.py` — 파일 크기 상한, `MAX_REGEN`, 기본 MCP 변환 도구 id.
- `src/infrastructure/agent_attachment/` — PDF/Word 업로드 + 산출 파일.

**프론트 (idt_front/)** — 업로드 위저드·미리보기·확정·폼 보유·유휴 재추천, `src/types`·`src/services`·`src/hooks`·`src/constants/api.ts`.

### 5-1. 테스트 (TDD)
- `tests/domain/document_extractor/` — 파일 검증, 슬롯 규칙, `MAX_REGEN`, **미근거 공란 판정(GB6)** 순수 단위.
- `tests/application/document_extractor/` — (A) extract(모의 MCP/LLM), refine 상한.
- `tests/application/agent_builder/` — (A) 생성 시 템플릿 `(agent_id, worker_id)` 저장·연결. (B) `document_extractor` 합성 노드 컴파일/실행(모의).
- `tests/infrastructure/document_extractor/` — 템플릿 repo CRUD(soft-delete 포함), MCP 어댑터(모의), 슬롯 추출, **토큰 치환 재현성**(같은 입력→같은 출력), 합성+`html→pdf`(원본 포맷). **GB6 검증: 근거 없는 슬롯이 공란·하이라이트로 남고 추정값이 생성되지 않는지**.
- 검증: `verify-architecture`, `verify-logging`, `verify-mcp-connections`, Windows 격리 pytest(CC 메모리).

### 5-2. Cross-Project (API 계약)
- 신규 `extract`/`refine` + 생성 payload 확장 → `/api-contract-sync` 필수. 엔드포인트 상수 `idt_front/src/constants/api.ts` 등록.

---

## 6. 작업 분해 — MVP 우선 단계화 (TDD: Red → Green → Refactor)

**Phase 1 (MVP 핵심) — (A) 빌드타임 추출·등록**
1. (Red/Green) domain: `schemas.py`/`policies.py`/`tool_config.py`(파일·슬롯·`MAX_REGEN`·GB6) → 구현.
2. (Red/Green) `tool_registry`에 `document_extractor` + `GET /agents/tools` 노출.
3. (Red/Green) infra: `DocumentConversionAdapter`(MCP pdf/doc→html), `SlotExtractor`(LLM) — 모의.
4. (Red/Green) app/api: `ExtractUseCase` + `POST /document-extractor/extract` + main.py DI.
5. (Red/Green) `document_template` 마이그레이션(`agent_id, worker_id` 종속) + repo. `create_agent`(+update) 템플릿 저장·연결.

**Phase 2 — (B) 런타임 실행(합성 + 파일 생성)**
6. (Red/Green) `Composer` + `DocumentConversionAdapter` `html→pdf/doc` + attachment 저장.
7. (Red/Green) `workflow_compiler` `document_extractor` **전용 합성 노드**: 지정 템플릿 로드 + 누적 컨텍스트 + 작성 지침 합성(value/generated, **GB6 공란**) → 파일 산출. `flow_hint` 유도.

**Phase 3 — 재요청 루프 + 5분 재생성**
8. (Red/Green) `RefineUseCase` + `POST /document-extractor/refine`(상한·로깅).

**Phase 4 — 프론트 + 계약 동기화**
9. `/api-contract-sync` → 타입/서비스/훅. 업로드 위저드·미리보기·확정·폼 보유·유휴 재추천.
10. (Refactor/verify) verify-architecture, verify-logging, verify-mcp-connections, 격리 pytest 전체.

---

## 7. 리스크 / 주의사항

| ID | 리스크 | 영향 | 대응 |
|----|--------|------|------|
| R1 | MCP `pdf/doc→html` 출력 HTML 품질 편차(복잡 표/양식 깨짐) → 슬롯 추출·복원 저하 | 高 | 미리보기+사람 확정 방어. refine 보정. 대표 문서로 Design 전 PoC. |
| R2 | LLM 슬롯 추출 오탐/누락 | 中 | 확정 필수(HITL). refine 재요청. 0개여도 수동 지정. |
| R3 | (실행) 값 슬롯 매핑 오류(엉뚱한 금액/날짜) | 高 | 채운 값 목록을 산출물에 병기. **미근거/미확인 값은 공란(GB6)** + 공란 표식. |
| R3a | (실행) 생성 슬롯(소견) 환각/근거 미부합 — 여신 문서 치명 | 高 | 생성 슬롯은 **상류 리서치 근거에만 기반** 프롬프트 제약 + 출처 병기. **근거 없으면 무조건 공란(GB6)** — 추정/작문 금지. |
| R3b | supervisor가 리서치 없이 곧장 합성(근거 누락) | 中 | `flow_hint`로 "근거 수집→합성" 유도. 근거 부재 슬롯은 공란 처리(GB6)되므로 잘못된 문서가 생성되지 않음. |
| R4 | (등록) 프론트 보유 상태 유실(새로고침/이탈) | 中 | 폼 임시 보존(드래프트). 유실 시 재추출 안내. |
| R5 | 유휴 5분 재생성 비용/무한 재호출 | 中 | `MAX_REGEN` 상한 + 로깅. 프론트 유휴 감지(선제 아님). |
| R6 | 템플릿 저장을 에이전트 생성 트랜잭션 편승 → 부분 실패 정합 | 中 | 동일 UseCase/세션 트랜잭션 원자성. CLAUDE.md 세션 규칙 준수. |
| R7 | 프론트 HTML 미리보기 XSS | 中 | sanitize/iframe sandbox. 신뢰 경계 명시(Design). |
| R8 | 산출 파일/원본 용량·TTL·권한 | 中 | 기존 attachment TTL/소유자(uploader==viewer) 재사용. |
| R9 | Windows pytest 교차 실행 flakiness | 低 | 격리 실행 검증(CC 메모리). |

---

## 8. Design 단계 확정/잔여

### 8-1. 확정된 결정 (rev.6)
| # | 항목 | 결정 |
|---|------|------|
| 1 | 슬롯 앵커링/치환 | **A — 플레이스홀더 토큰**. 확정 시 샘플값을 `{{key}}`로 치환해 `html_skeleton` 저장, 런타임 문자열 치환(재현성 100%). |
| 3 | MCP 도구 id 지정 | **`DocumentExtractorToolConfig`에 명시 저장**(pdf→html, html→pdf). 변환은 MCP만 꽂아 사용. |
| 4 | 출력 포맷 | **원본 포맷 따름** — PDF→PDF, Word→Word. |
| 6 | 공란 표식 | **하이라이트**로 표시해 사람이 처리. |
| 7 | 삭제 정합 | **soft-delete**(`status='deleted'`). |
| 8 | 원본 파일 | **보관**(`source_file_ref`). |
| 2(저장) | 슬롯 저장 형태 | **JSON** — `document_template.slots`에 슬롯 배열을 통째로 저장(자식 테이블 아님). 슬롯은 항상 템플릿과 함께 로드/치환되므로 조인 불필요. |

### 8-2. 잔여 (Design에서 확정)
1. **작성 지침 위치** — 합성 노드 프롬프트 인라인(현재 기본) vs 도구 config 편집 필드. (범용 지침 필요 시 Skill 분리는 후속.)
2. **토큰화 실행 지점** — 확정 시 프론트가 토큰 치환한 `html_skeleton`을 보내는가, 백엔드(confirm/save)에서 슬롯 앵커로 치환하는가.
3. **원본 파일 TTL/권한** — 보관하되 보존 기간·접근 권한(uploader==viewer 재사용 여부).

---

## 9. 다음 단계

```
/pdca design document-template-extractor
```
