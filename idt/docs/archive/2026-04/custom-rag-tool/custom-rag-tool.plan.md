# Plan: 커스텀 RAG 도구 (Custom RAG Tool for Agent Builder)

> Feature ID: CUSTOM-RAG-TOOL-001  
> Created: 2026-04-21  
> Status: Draft  
> Priority: High

---

## 1. 배경 (Background)

### 현재 상태

- 에이전트 빌더(커스텀/자동)에서 `internal_document_search` 도구를 선택하면 **시스템 전체 문서**를 대상으로 BM25+Vector 하이브리드 검색 수행
- `HybridSearchUseCase`는 고정된 ES 인덱스(`es_index`)와 Qdrant 전체 컬렉션을 사용
- RAG 도구의 검색 범위, top_k, 검색 모드 등을 에이전트별로 커스텀할 수 없음
- `tool_registry.py`에 `internal_document_search`가 단일 고정 항목으로 등록됨

### 문제점

1. **검색 범위 제한 불가**: 특정 부서 문서, 특정 카테고리 문서만 검색하는 에이전트를 만들 수 없음
2. **파라미터 고정**: top_k=5, rrf_k=60 등이 하드코딩되어 에이전트 용도에 맞는 튜닝 불가
3. **다중 RAG 도구 불가**: 하나의 에이전트에서 "정책 문서 검색"과 "기술 문서 검색"을 별도 도구로 구성할 수 없음

---

## 2. 목표 (Objectives)

사용자가 에이전트를 생성할 때 RAG 도구의 **검색 범위와 동작 파라미터를 커스텀 설정**할 수 있게 한다.

### 핵심 목표

| # | 목표 | 측정 기준 |
|---|------|----------|
| G1 | 에이전트별 RAG 검색 범위 지정 | 컬렉션/메타데이터 필터 설정 가능 |
| G2 | RAG 파라미터 커스텀 | top_k, 검색 모드(hybrid/vector/bm25) 설정 가능 |
| G3 | 다중 RAG 도구 구성 | 한 에이전트에 서로 다른 범위의 RAG 도구 2개 이상 추가 가능 |
| G4 | 기존 호환성 유지 | 기존 `internal_document_search` 동작 변경 없음 |

---

## 3. 범위 (Scope)

### In-Scope (구현 대상)

#### 3-1. RAG 도구 설정(Configuration) 스키마

- **검색 범위 필터**
  - `collection_name`: Qdrant 컬렉션 지정 (기본값: 시스템 기본 컬렉션)
  - `es_index`: ES 인덱스 지정 (기본값: 시스템 기본 인덱스)
  - `metadata_filter`: 메타데이터 기반 필터링 (예: `{"department": "finance"}`, `{"category": "policy"}`)
- **검색 파라미터**
  - `top_k`: 반환 결과 수 (기본값: 5, 범위: 1-20)
  - `search_mode`: `hybrid` | `vector_only` | `bm25_only` (기본값: hybrid)
  - `rrf_k`: RRF 병합 파라미터 (기본값: 60)
- **도구 표시 설정**
  - `tool_name`: 에이전트 내 도구 표시명 (예: "금융 정책 검색")
  - `tool_description`: LLM이 도구 사용 판단 시 참고할 설명

#### 3-2. 백엔드 변경

- `ToolMeta` 스키마에 `config` 필드 추가 (RAG 도구용 설정 저장)
- `agent_tool` 테이블에 `tool_config` JSON 컬럼 추가
- `ToolFactory.create()` / `create_async()`에서 config 기반 RAG 도구 인스턴스 생성
- `InternalDocumentSearchTool`에 필터/파라미터 주입 지원
- `HybridSearchRequest`에 메타데이터 필터 전달 경로 추가
- Auto Agent Builder의 `AgentSpecInferenceService`에서 RAG config 추론 지원

#### 3-3. 프론트엔드 변경

- 에이전트 빌더 UI에서 RAG 도구 선택 시 **설정 패널** 노출
  - 검색 범위 선택 (컬렉션/인덱스 드롭다운)
  - 메타데이터 필터 입력
  - 검색 파라미터 조정 (top_k 슬라이더, 검색 모드 라디오)
  - 도구 이름/설명 커스텀 입력
- 에이전트 상세 조회 시 RAG 설정 표시

#### 3-4. API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/v1/rag-tools/collections` | 사용 가능한 컬렉션/인덱스 목록 |
| GET | `/api/v1/rag-tools/metadata-keys` | 필터링 가능한 메타데이터 키 목록 |
| (기존) POST | `/api/v1/agents` | `tools[].config` 필드로 RAG 설정 전달 |
| (기존) PATCH | `/api/v1/agents/{id}` | RAG 설정 수정 |

### Out-of-Scope (이번 범위 밖)

- 사용자별 개인 문서 업로드 및 개인 RAG 컬렉션 생성
- RAG 도구 성능 모니터링/분석 대시보드
- 실시간 검색 미리보기 (도구 설정 중 테스트 검색)
- Qdrant 컬렉션 동적 생성/삭제 API

---

## 4. 사용자 스토리 (User Stories)

### US-1: RAG 도구 포함 에이전트 생성

> **As a** 에이전트 빌더 사용자  
> **I want** 에이전트 생성 시 RAG 도구의 검색 범위를 지정하고 싶다  
> **So that** 특정 부서/카테고리 문서만 검색하는 전문 에이전트를 만들 수 있다

**인수 조건:**
- 에이전트 생성 폼에서 RAG 도구 선택 시 설정 패널이 나타난다
- 컬렉션, 메타데이터 필터, top_k, 검색 모드를 설정할 수 있다
- 설정 없이도 기본값으로 생성 가능하다 (기존과 동일 동작)

### US-2: 다중 RAG 도구 구성

> **As a** 에이전트 빌더 사용자  
> **I want** 하나의 에이전트에 서로 다른 범위의 RAG 도구를 여러 개 추가하고 싶다  
> **So that** "금융 정책 검색"과 "기술 매뉴얼 검색"을 구분하여 사용하는 에이전트를 만들 수 있다

**인수 조건:**
- 같은 `internal_document_search` 기반이지만 서로 다른 config를 가진 도구를 복수 추가 가능
- 각 도구는 고유한 `tool_name`과 `tool_description`을 가진다
- LLM이 질문 맥락에 따라 적절한 RAG 도구를 선택한다

### US-3: 자동 에이전트 빌더에서 RAG 설정 추론

> **As a** 자동 에이전트 빌더 사용자  
> **I want** "금융 관련 문서만 검색하는 에이전트 만들어줘"라고 요청하면 RAG 설정이 자동 구성되길 원한다  
> **So that** 수동 설정 없이도 적절한 RAG 도구가 구성된다

**인수 조건:**
- 사용자 요청에서 검색 범위 힌트를 추출하여 metadata_filter 자동 설정
- 확신도 부족 시 "어떤 문서를 검색 대상으로 할까요?" 등의 clarifying question 생성
- 사용 가능한 컬렉션/메타데이터 키 목록을 LLM 프롬프트에 포함

---

## 5. 기술 분석 (Technical Analysis)

### 5-1. 영향받는 파일 (백엔드)

| Layer | File | 변경 내용 |
|-------|------|----------|
| Domain | `domain/agent_builder/schemas.py` | `ToolMeta`에 `config: dict` 필드 추가 |
| Domain | `domain/agent_builder/tool_registry.py` | RAG 도구 config 스키마 정의 |
| Domain | `domain/hybrid_search/schemas.py` | `HybridSearchRequest`에 `metadata_filter` 추가 |
| Application | `application/rag_agent/tools.py` | `InternalDocumentSearchTool`에 config 주입 |
| Application | `application/hybrid_search/use_case.py` | 메타데이터 필터 적용 로직 |
| Application | `application/auto_agent_builder/agent_spec_inference_service.py` | RAG config 추론 프롬프트 |
| Infrastructure | `infrastructure/agent_builder/tool_factory.py` | config 기반 도구 생성 |
| Infrastructure | `infrastructure/agent_builder/models.py` | `agent_tool.tool_config` 컬럼 |
| Infrastructure | `infrastructure/retriever/qdrant_retriever.py` | 컬렉션/필터 파라미터 전달 |
| Interfaces | `api/routes/agent_builder_router.py` | 요청/응답에 config 포함 |
| Interfaces | `interfaces/schemas/` | RAG config 요청/응답 스키마 |

### 5-2. 영향받는 파일 (프론트엔드)

| 위치 | 변경 내용 |
|------|----------|
| `src/types/tool.ts` | `ToolConfig` 타입 추가 |
| `src/pages/AgentBuilderPage/` | RAG 설정 패널 컴포넌트 |
| `src/services/agentService.ts` | config 필드 포함한 API 호출 |
| `src/constants/api.ts` | 새 엔드포인트 상수 |

### 5-3. DB 스키마 변경

```sql
-- agent_tool 테이블에 config 컬럼 추가
ALTER TABLE agent_tool 
ADD COLUMN tool_config JSON DEFAULT NULL 
COMMENT 'RAG 등 도구별 커스텀 설정 (JSON)';
```

### 5-4. RAG Tool Config 스키마 (예시)

```python
@dataclass(frozen=True)
class RagToolConfig:
    collection_name: str | None = None      # Qdrant 컬렉션
    es_index: str | None = None             # ES 인덱스
    metadata_filter: dict[str, str] = {}    # 메타데이터 필터
    top_k: int = 5                          # 결과 수
    search_mode: str = "hybrid"             # hybrid | vector_only | bm25_only
    rrf_k: int = 60                         # RRF 파라미터
    tool_name: str = "내부 문서 검색"        # 커스텀 도구명
    tool_description: str = ""              # 커스텀 도구 설명
```

---

## 6. 리스크 및 완화 (Risks & Mitigation)

| 리스크 | 영향 | 완화 방안 |
|--------|------|----------|
| 잘못된 metadata_filter로 검색 결과 0건 | 에이전트 품질 저하 | 설정 시 유효성 검증 + 경고 메시지 |
| 다중 RAG 도구 시 LLM 혼동 | 잘못된 도구 선택 | tool_description에 명확한 구분 기준 필수화 |
| tool_config JSON 스키마 변경 시 하위 호환 | 기존 에이전트 오류 | config 필드 기본값 설정, 마이그레이션 스크립트 |
| Qdrant 컬렉션명 노출 | 내부 구조 유출 | 프론트에서 alias 사용, 실제 컬렉션명은 백엔드만 관리 |

---

## 7. 구현 순서 (Implementation Order)

| Phase | 작업 | 의존성 |
|-------|------|--------|
| 1 | Domain 스키마 정의 (`RagToolConfig`, `HybridSearchRequest` 확장) | 없음 |
| 2 | DB 마이그레이션 (`agent_tool.tool_config`) | Phase 1 |
| 3 | `ToolFactory` config 기반 도구 생성 + `InternalDocumentSearchTool` 확장 | Phase 1 |
| 4 | `HybridSearchUseCase` 메타데이터 필터 적용 | Phase 1 |
| 5 | API 엔드포인트 (컬렉션 목록, 메타데이터 키 목록) | Phase 4 |
| 6 | 에이전트 생성/수정 API에 config 전달 경로 추가 | Phase 2, 3 |
| 7 | Auto Agent Builder RAG config 추론 | Phase 5, 6 |
| 8 | 프론트엔드 RAG 설정 패널 | Phase 5, 6 |

---

## 8. 성공 기준 (Success Criteria)

- [ ] 에이전트 생성 시 RAG 도구에 메타데이터 필터를 설정하면 해당 범위만 검색됨
- [ ] 기존 config 없는 에이전트는 전체 문서 검색 (하위 호환)
- [ ] 다중 RAG 도구를 가진 에이전트가 질문에 따라 올바른 도구를 선택함
- [ ] 자동 에이전트 빌더에서 "금융 문서만 검색" 요청 시 적절한 config가 생성됨
- [ ] 모든 변경에 대한 TDD 테스트 통과

---

## 9. 참고 (References)

- 기존 에이전트 빌더: `docs/archive/2026-03/custom-agent-builder/`
- 자동 에이전트 빌더: `docs/archive/2026-03/auto-agent-builder/`
- 하이브리드 검색: `src/application/hybrid_search/use_case.py`
- 도구 팩토리: `src/infrastructure/agent_builder/tool_factory.py`
- 도구 레지스트리: `src/domain/agent_builder/tool_registry.py`
