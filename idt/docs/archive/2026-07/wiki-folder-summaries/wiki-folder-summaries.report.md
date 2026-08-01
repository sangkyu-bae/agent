# wiki-folder-summaries 완료 보고서

> **Summary**: 에이전트 위키의 쓰기 시점 폴더 요약 계층 구현 완료
>
> **Feature**: wiki-folder-summaries
> **Cycle**: Plan → Design → Do → Check (2026-07-25, 단일 사이클)
> **Match Rate**: 100% (1차 96.7% → 갭 3건 즉시 조치)
> **Author**: 배상규
> **Completed**: 2026-07-25

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **Feature** | wiki-folder-summaries: 에이전트 위키 폴더 요약 계층 (쓰기 시점 증류) |
| **기간** | 2026-07-25 ~ 2026-07-25 (단일 사이클) |
| **선행 기능** | wiki-agentic-navigation (archive, Match 100%) |
| **Match Rate** | 100% (1차 96.7% → 갭 3건 즉시 조치) |
| **상태** | ✅ 완료, 배포 준비 완료 (V053 선행 필수) |

### 1.2 결과 요약

| 구분 | 수량 |
|------|-----:|
| **신규 파일** | 10개 (1 SQL + 1 repo abstract + 5 구현 + 3 테스트) |
| **수정 파일** | 11개 (entity/policy + service/distiller/tool + provider/compiler + config/DI) |
| **신규 테스트** | 43건 (domain 1 + infra 13 + app 6 + agent_run 4 + 도구/compiler/rendering 19) |
| **회귀 테스트** | 0건 실패 (실패 의심 전건 master 대조로 기존 문제 확정) |
| **위키 전체 스윕** | 251 passed (조치 반영 후) |
| **광역 회귀** | application + domain 4,024 passed |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | flat 목차 상한(`wiki_toc_max_items=50`) 초과 시 목록 절단, LLM은 뒷부분 존재 모름. 문서 단위 나열로 프롬프트 비용 선형 증가 — wiki-agentic-navigation의 후속 진화 필요 |
| **Solution** | 승인/편집/폐기 이벤트 시 해당 폴더(path) 설명을 LLM으로 증류해 저장, 상위 폴더로 전파(깊이≤3 → 최대 2단). 목차 블록을 "폴더 요약 목록"으로 교체, `wiki_list(path)` 도구로 폴더 진입 → 문서 목록 → `wiki_read` 뎁스 탐색 체인 완성 |
| **Function/UX Effect** | 위키가 수백 건이어도 프롬프트에는 폴더 요약 십수 줄만 상주. 에이전트는 "지도(최상위 폴더 요약) → 구역(wiki_list로 진입) → 문서(wiki_read 열람)" 순서로 사람처럼 탐색. 탐색 전 과정이 `ai_tool_call`에 자동 기록되어 결정적으로 관측 가능. Eventually consistent 계약: 요약은 탐색 힌트, 진실은 wiki_list의 실시간 문서 목록(마이그레이션 요약 stale 시에도 목록 정확성 보장) |
| **Core Value** | 라우팅 검색 4부작(청킹→섹션→문서 요약→라우팅)의 "쓰기 시점 요약 계층" 설계 사상을 위키에 적용. 질의 시점 비용을 상수로 고정하고, 요약 품질은 승인 이벤트마다 갱신되는 구조. 다음 진화(deep-wiki-research) 기반 마련 |

---

## 1. PDCA 사이클 요약

### 1.1 Plan (2026-07-25)
- **문서**: `docs/01-plan/features/wiki-folder-summaries.plan.md` (v0.1)
- **목표**: 
  - 쓰기 시점 폴더 요약 계층 추가
  - 목차 블록의 폴더 모드 (문서 수와 무관한 상수 프롬프트 크기)
  - `wiki_list(path)` 도구 구현
  - 무회귀 점진 전환 (임계 이하 flat 유지)
- **예상 기간**: 1일

### 1.2 Design (2026-07-25)
- **문서**: `docs/02-design/features/wiki-folder-summaries.design.md` (v0.2, as-built 정정 포함)
- **확정 설계 결정 (D1~D8)**:
  - **D1**: 신규 테이블 `wiki_folder_summary` (V053, agent_id+path 유니크)
  - **D2**: WikiFeedbackService 팬아웃 패턴 (fire-and-forget, 최적 best-effort)
  - **D3**: 계층 증류 (RAPTOR식, leaf=문서 500자 cap, parent=하위 요약, 총 20,000자 절단)
  - **D4**: `wiki_list` 도구 (WikiReadTool 패턴 복제, FAIL_TEXT 오라클 차단)
  - **D5**: 목차 폴더 모드 (임계 초과 시에만 전환, flat 폴백)
  - **D6**: 워커 구성 (wiki_list 동봉, 이중 주입 계약 유지)
  - **D7**: 관측 (배선 0, UsageCallback 기존 경로 재사용)
  - **D8**: DI 조립 (api/main.py에 모든 의존성 주입)
- **DDL 규칙**: 테이블 생성 시 **전 컬럼+테이블에 COMMENT 항상 부여** (2026-07-25 사용자 지시, 최초 적용)

### 1.3 Do (2026-07-25)
- **구현 기간**: 실제 1일 (Plan 예상과 일치)
- **실제 구현 순서** (TDD Red→Green):
  1. domain: `WikiFolderSummary` dataclass
  2. infra-모델/repo: WikiFolderSummaryModel + MySQLWikiFolderSummaryRepository (upsert/delete/list_by_agent)
  3. infra-증류기: FolderSummaryDistiller (fake llm로 입력 절단·계층 조립 검증)
  4. app-서비스: WikiFolderSummaryService (조상 확장·bottom-up 순서·폴더 단위 실패 격리)
  5. 훅: WikiReviewUseCase/WikiHumanWriteUseCase optional 주입 + kickoff 호출
  6. 도구: WikiListTool (격리·오라클 차단·루트/하위/미분류 렌더)
  7. 레지스트리/팩토리: wiki_list 등록 + case 분기
  8. 렌더/프로바이더: render_wiki_folder_block + WikiTocProvider 분기
  9. 컴파일러: wiki_read 워커 wiki_list 동봉 + 폴더 모드 지시
  10. DI/config: main.py 조립 + V053 작성

### 1.4 Check (2026-07-25)
- **분석 문서**: `docs/03-analysis/wiki-folder-summaries.analysis.md`
- **1차 Match Rate**: 96.7% (14.5/15)
- **1차 발견 갭 (4건)** → **즉시 조치**:
  - **G1** (낮음, 기능 동치): 설계 D1의 `list_children` repo 메서드 → 실제 구현은 `list_by_agent`+호출측 prefix 필터 (폴더 수 작아서 호출측 단순성 이득). **조치**: 설계 v0.2 as-built 정정 문서화
  - **G2** (낮음): `_run_guarded`가 전체를 감싸 leaf 실패 시 조상 갱신 중단 (설계는 폴더 단위 격리 문언). **조치**: `_refresh_one` 분리 + 폴더 루프 내 try/except + 검증 테스트 `test_leaf_failure_does_not_block_ancestors` 추가
  - **G3** (낮음): 폴더 모드 supervisor 지도 블록 주입 명시 단언 테스트 부재. **조치**: 테스트 `test_folder_block_also_prepended_to_supervisor` 추가
  - **G4** (없음): FAIL_TEXT 문구·설정명 설계-코드 상이. **조치**: 설계 v0.2에서 실제 값으로 정정
- **최종 Match Rate**: **100%**

---

## 2. 완료 항목

### 2.1 신규 파일 (10개)

#### 데이터 계층
1. **db/migration/V053__create_wiki_folder_summary.sql** (57줄)
   - 테이블: wiki_folder_summary (id PK, agent_id, path, summary TEXT, article_count INT, updated_at)
   - 유니크: `uq_wiki_folder(agent_id, path)`
   - FK/COLLATE 명시 없음 (V037 선례, engine=InnoDB)
   - 전 컬럼+테이블 COMMENT 부여 (DDL 규칙 최초 적용)

2. **src/application/repositories/wiki_folder_repository.py** (신규 파일)
   - 추상 인터페이스: WikiFolderSummaryRepository
   - 메서드: upsert(summary), delete(agent_id, path), list_by_agent(agent_id)

#### 도메인 / 정책 강화
3. **src/domain/wiki/entity.py** (추가 라인)
   - WikiFolderSummary dataclass (id, agent_id, path, summary, article_count, updated_at)
   - 파생 데이터 표시, 상태 전이 메서드 없음

4. **src/domain/wiki/policies.py** (추가 라인)
   - WikiPolicy.expand_ancestors(path) → [path, parent_path, grandparent_path, ...] (깊이≤3)
   - 도메인 정책 계층으로 배치 (서비스 아님)

#### 인프라 구현
5. **src/infrastructure/wiki/folder_summary_repository.py** (신규 파일)
   - MySQLWikiFolderSummaryRepository 구현
   - upsert: MySQL `INSERT ... ON DUPLICATE KEY UPDATE` (SQLAlchemy dialect)
   - delete: 파라미터화 WHERE절
   - list_by_agent: agent_id 필터 + 정렬

6. **src/infrastructure/wiki/folder_summary_distiller.py** (신규 파일)
   - FolderSummaryDistiller 클래스 (WikiDistiller 구조 복제)
   - 시스템 프롬프트: "폴더 안내 설명 2~3문장" (개별 문서 나열 금지)
   - from_openai 팩토리, _coerce_text 재사용
   - 입력: leaf=title+content[:500], parent=문서+하위_요약들, 총 절단 20,000자

7. **src/application/wiki/folder_summary_service.py** (신규 파일)
   - WikiFolderSummaryService: kickoff_refresh(agent_id, paths, request_id) → None
   - asyncio.create_task(_run_guarded(...)) (fire-and-forget, 팬아웃 패턴 재사용)
   - _refresh_one(path): 폴더 단위 실패 격리 (try/except)
   - bottom-up 순서 (깊은 경로부터), 0건 폴더 삭제, enabled 게이트

8. **src/infrastructure/wiki/wiki_list_tool.py** (신규 파일)
   - WikiListTool(BaseTool) 구현
   - args: path (""=루트)
   - 하위 폴더 요약(prefix 필터) + 해당 path 직속 승인 문서(실시간)
   - FAIL_TEXT: "요청한 위키 폴더를 찾을 수 없거나 비어 있습니다." (오라클 차단)

#### 테스트 (신규 8개 파일)
9. **tests/domain/wiki/test_folder_summary.py**
   - WikiFolderSummary 생성·필드 테스트

10. **tests/infrastructure/wiki/test_folder_summary_repository.py**
    - MySQL upsert/delete/list_by_agent 계약 검증

11. **tests/infrastructure/wiki/test_folder_summary_distiller.py**
    - 입력 절단·계층 조립 단언

12. **tests/application/wiki/test_folder_summary_service.py**
    - 조상 확장·bottom-up 순서·0건 삭제·폴더 단위 실패 격리·enabled 게이트

13. **tests/application/wiki/test_toc_provider_folder_mode.py**
    - render_wiki_folder_block + flat 폴백 검증

14. **tests/application/agent_builder/test_tool_factory.py** (선행 동치)
    - wiki_list 케이스 분기 + ValueError 검증

15. **tests/application/agent_builder/test_workflow_compiler_wiki_toc.py** (확장)
    - 폴더 모드에서 wiki_list 도구 동봉
    - supervisor/워커 지도 블록 이중 주입 단언

16. **tests/application/agent_run/test_wiki_folder_block.py**
    - 조립 테스트: 폴더 모드 end-to-end 검증

### 2.2 수정 파일 (11개)

#### 도메인 / 정책
1. **src/domain/wiki/entity.py**
   - WikiFolderSummary 추가 (5줄)

2. **src/domain/wiki/policies.py**
   - expand_ancestors 추가 (10줄)

#### 애플리케이션 / 서비스
3. **src/application/wiki/interfaces.py**
   - FolderSummaryDistillerInterface 추가 (추상 인터페이스)

4. **src/application/wiki/review_use_case.py**
   - _to_approved/edit/_to_deprecated 후 folder_service.kickoff_refresh (20줄 추가)
   - optional 의존성 (기본 None)

5. **src/application/wiki/human_write_use_case.py**
   - create/update/deprecate 후 folder_service.kickoff_refresh (25줄 추가)
   - update에서 path 이동 시 [old_path, new_path] 둘 다 전파
   - optional 의존성 (기본 None)

6. **src/application/wiki/toc_provider.py**
   - render_block: 폴더 모드 분기 추가 (폴더 요약 존재 + 임계 초과 시)
   - flat 폴백 (50줄 수정)

#### 인프라 모델
7. **src/infrastructure/wiki/models.py**
   - WikiFolderSummaryModel 추가 (SQLAlchemy ORM 모델, comment= 동일 반영)

#### 프롬프트 / 렌더
8. **src/application/agent_run/prompt_rendering.py**
   - render_wiki_folder_block 함수 추가 (폴더 지도 렌더)
   - WIKI_FOLDER_HEADER_TAG 상수 추가 (모드 감지)
   - 지도 max_bytes 절단 + "(전체 N개 중 M개 표시)" 고지

#### 워크플로 / 컴파일러
9. **src/application/agent_builder/workflow_compiler.py**
   - wiki_read 워커 생성 시 폴더 모드일 때 tools=[wiki_read, wiki_list] 동봉 (30줄 수정)
   - 워커 prompt = (폴더 지도 or flat 목차) + 모드별 지시

#### 도구 / 레지스트리
10. **src/domain/agent_builder/tool_registry.py**
    - TOOL_REGISTRY에 "wiki_list" 등록

11. **src/infrastructure/agent_builder/tool_factory.py**
    - case "wiki_list": wiki_session_factory + folder_repo_builder 주입

#### 설정 / DI
12. **src/config.py** (as-built: 수정 포함)
    - wiki_folder_summaries_enabled: bool = False (기본 off, 마이그레이션 선행 필수)
    - wiki_folder_mode_threshold: int = 30 (임계값, additive)

13. **src/api/main.py**
    - folder_repo_builder, folder_distiller, folder_service 생성 및 DI 조립
    - WikiReviewUseCase, WikiHumanWriteUseCase, WikiTocProvider, ToolFactory에 의존성 주입

---

## 3. 설계 결정 하이라이트

### 3.1 8가지 핵심 결정 (D1~D8)

| 항목 | 결정 | 근거 |
|------|------|------|
| **D1. 저장 모델** | 신규 테이블 `wiki_folder_summary` | 폴더 요약은 승인 게이트·출처 관리가 없는 파생 데이터 → 문서와 라이프사이클 다름 |
| **D2. 재증류 트리거** | WikiFeedbackService 팬아웃 (fire-and-forget) | 최적 best-effort → 승인 API 지연 없음, 인프라 추가 0 |
| **D3. 증류 입력** | RAPTOR식 계층 증류 (leaf=500자 cap, parent=요약들, 총 20K절단) | 토큰 상한 안정 + 계층 구조 보존 |
| **D4. wiki_list 도구** | WikiReadTool 패턴 복제, FAIL_TEXT 오라클 차단 | 일관성 + 보안 (id 유추 방어) |
| **D5. 목차 모드** | 임계 초과 시에만 전환, flat 폴백 | 무회귀 점진 전환, 기존 소규모 에이전트 무영향 |
| **D6. 워커 구성** | wiki_list 동봉, 이중 주입 계약 유지 | "지도→진입→열람" 체인이 한 react 루프에서 완성 |
| **D7. 관측** | 배선 0 (UsageCallback 기존 경로 재사용) | ai_tool_call에 자동 기록, 추가 코드 불필요 |
| **D8. DI 조립** | api/main.py에 모든 의존성 수렴 | 결정 6개 구현 + 기존 구조 정합 |

### 3.2 Eventually Consistent 계약

- **요약은 탐색 힌트**: 증류 실패·stale 가능 → updated_at 노출
- **진실은 wiki_list의 실시간 문서 목록**: 마이그레이션/편집 시에도 목록은 실시간 쿼리로 정확성 보장
- **다음 전이에서 수렴**: 문서 승인·편집 시 폴더 요약 재생성으로 정합성 회복

### 3.3 무회귀 배포 전략

- **기본값**: `wiki_folder_summaries_enabled=False` → 코드만 먼저 배포 가능 (V053 선행 필수)
- **전환 조건**: 관리자가 enabled=True + E2E 수동 검증 후
- **기존 기능 보호**: 임계 이하(30) 에이전트는 flat 목차 유지, 기존 테스트 무수정 통과

---

## 4. 검증 결과

### 4.1 단위 테스트 (TDD Red→Green)

| 계층 | 테스트 수 | 상태 | 주요 검증 |
|------|------:|:---:|----------|
| domain (entity/policy) | 1 | ✅ | WikiFolderSummary 생성, expand_ancestors |
| infrastructure (model/repo/distiller) | 13 | ✅ | upsert/delete/list 계약, 입력 절단, 계층 조립 |
| application (service/interfaces) | 6 | ✅ | 조상 확장, bottom-up 순서, 폴더 단위 격리, 0건 삭제, enabled 게이트 |
| agent_run (wiki block/tool factory) | 4 | ✅ | 도구 렌더, 레지스트리 동기화, 폴더/flat 분기 |
| 렌더/컴파일러 (prompt/workflow) | 19 | ✅ | wiki_folder_block 렌더, 이중 주입, wiki_list 동봉, 폴더 모드 지시 |
| **합계** | **43** | ✅ | 모두 green |

### 4.2 회귀 테스트

| 범위 | 결과 | 비고 |
|------|:---:|------|
| 위키 전체 스윕 | 251 passed | 조치 반영 후 |
| application + domain 광역 | 4,024 passed | 환경 격리 실행 |
| 선행 기능 (wiki-agentic-navigation) | 모두 무수정 통과 | flat 목차·wiki_read 기존 경로 무영향 |
| **실패 의심 전건** | 0 (master 대조로 기존 문제 확정) | langgraph Mock inspect 등 환경성 이슈 |

### 4.3 설계-구현 일치도 (Gap Analysis)

| 항목 | 1차 | 즉시 조치 | 최종 |
|------|:---:|:---:|:---:|
| FR-01~FR-07 (기능 요구사항) | 14.5/15 (96.7%) | +0.5 | **15/15 (100%)** |
| D1~D8 (설계 결정) | 8/8 구현 | 설계 v0.2 정정 | **8/8 검증** |

---

## 5. 1차 갭 조치 상세

### G1: list_children vs list_by_agent 설계-구현 상이

**발견**: 설계 D1은 `WikiFolderSummaryRepository.list_children(agent_id, path)`로 직속 하위 폴더만 반환 예상, 실제 구현은 `list_by_agent(agent_id)` 전체 조회 + 호출측 prefix 필터

**조치**: 설계 v0.2 as-built 정정 문서 (§1, D1 후반)
- "직속 하위 폴더 선별은 repo 메서드가 아니라 호출 측 prefix 필터(서비스 `_load_children` / 도구 `_is_direct_child`)로 한다"
- **근거**: 에이전트당 폴더 수가 작음(깊이≤3) → SQL LIKE 이중 조건보다 호출측 단순성 이득

**영향**: 무한 (서비스·도구 내부 구현만, 계약 동일)

### G2: 폴더 단위 실패 격리 미흡

**발견**: `_run_guarded`가 refresh 전체를 감싸면, leaf 폴더 증류 실패 시 같은 배치의 조상 폴더 갱신이 중단됨 (설계 D2는 "폴더 단위 격리" 문언)

**조치**: 코드 보강 (folder_summary_service.py)
1. `_refresh_one(path)` 분리 → 폴더별 독립 증류
2. 폴더 루프 내 try/except로 한 폴더 실패 시 다음 진행
3. 검증 테스트 `test_leaf_failure_does_not_block_ancestors` 추가

**변경 라인**: ~15줄

**영향**: 강건성 개선 (부분 실패도 부분 갱신)

### G3: supervisor 지도 블록 이중 주입 단언 테스트 부재

**발견**: 폴더 모드에서 supervisor prompt에도 폴더 지도 블록이 주입되는지 명시 단언 테스트 없음 (구조상 같은 변수지만 명시화 필요)

**조치**: 테스트 추가 (test_workflow_compiler_wiki_toc.py)
- `test_folder_block_also_prepended_to_supervisor`: 폴더 모드에서 `output["supervisorPrompt"]`가 지도 블록 포함 검증

**영향**: 테스트 커버리지 + 설계 D6 계약 고정

### G4: FAIL_TEXT·설정명 설계-코드 상이

**발견**: 
- 설계: FAIL_TEXT = "요청한 위키 폴더를 찾을 수 없거나 비어 있습니다."
- 코드: 정확 (github에서 확인)
- 설계: `settings.wiki_model` 참조
- 코드: `settings.openai_llm_model` (실존하는 이름)

**조치**: 설계 v0.2에서 실제 값으로 정정 (코드가 더 정확, 설계 업데이트)

**영향**: 없음 (문서 정정만)

---

## 6. 무해한 초과 구현 (채택 유지)

| 항목 | 의도 | 영향 |
|------|------|------|
| 환각 방어 문장 | 폴더 지도 헤더에 "지도만으로 답하지 말고 wiki_list로 진입하세요" | LLM 가이더 강화 ✅ |
| 지도 절단 고지 | max_bytes 초과 시 "(전체 N개 중 M개 표시)" | 투명성 증대 ✅ |
| expand_ancestors 도메인 배치 | 정책 계층(서비스 아님) | 책임 명확 ✅ |
| path 정규화 | wiki_list args에 `strip("/")` | LLM 입력 관용 ✅ |
| reject() 재증류 트리거 | draft→deprecated도 kickoff_refresh | 무해 (승인 집합 무변화) |

---

## 7. 설계 의사결정 교훈

### 7.1 Eventually Consistent가 필요한 이유

선행 기능 wiki-agentic-navigation에서 "목차는 힌트, 진실은 런타임 검색"이라는 패턴이 성공했기 때문. 폴더 요약도 동일 패턴을 적용:
- 요약은 전문(프롬프트 상주)
- 실시간 목록은 wiki_list 도구가 보장
- 다음 전이에서 수렴

### 7.2 fire-and-forget 팬아웃의 가치

승인 API 지연 없음 + best-effort 실패 처리로, 극단적 경우에도:
- LLM 키 미설정 → warning 로그만, 승인 성공
- 네트워크 실패 → 다음 편집 시 재시도
- 인프라 추가 0 → 기존 WikiFeedbackService 패턴 재사용

### 7.3 폴더 단위 실패 격리의 중요성

한 경로 증류 실패(예: root) → 조상(예: root > vendor > utils)까지 전부 중단되는 문제 발생 가능. 폴더 루프 내 try/except로 해결:
```python
for path in paths_to_refresh:
    try:
        _refresh_one(path)
    except Exception:
        logger.warning(f"폴더 {path} 갱신 실패", exc_info=True)
        # 다음 폴더 진행
```

### 7.4 DDL COMMENT 규칙의 첫 적용

마이그레이션 V053이 첫 사례. 향후 신규 테이블 생성 시 **모든 컬럼과 테이블에 COMMENT 필수**:
```sql
CREATE TABLE wiki_folder_summary (
    id CHAR(36) NOT NULL COMMENT 'UUID PK',
    ...
) COMMENT='에이전트 위키 폴더 요약 — ...'
```

이유: 스키마 자명성 + SQLAlchemy 모델에도 동일 반영으로 코드-DB 정합성

---

## 8. 완료된 요구사항 (FR 추적)

| FR | 요구사항 | 구현 위치 | 상태 |
|----|---------|---------|:---:|
| **FR-01** | wiki_folder_summary 테이블 + 모델 + V053 (agent_id+path 유니크) | V053, models.py, folder_summary_repository.py | ✅ |
| **FR-02** | 폴더 요약 증류: 상태 전이 시 재증류 + 조상 전파, LLM 실패 best-effort | folder_summary_service.py, review/human_write_use_case.py | ✅ |
| **FR-03** | wiki_list 도구: 하위 폴더+문서 목록, agent_id 격리, FAIL_TEXT 오라클 차단 | wiki_list_tool.py, tool_registry.py, tool_factory.py | ✅ |
| **FR-04** | 목차 블록 폴더 모드: 폴더 요약 렌더 + flat 폴백, 임계 config | render_wiki_folder_block, toc_provider.py, config.py | ✅ |
| **FR-05** | 워커 지시 갱신 + 이중 주입 유지 | workflow_compiler.py (wiki_list 동봉), prompt_rendering.py | ✅ |
| **FR-06** | 관측 배선 0: wiki_list 호출이 ai_tool_call에 자동 기록 | (UsageCallback 기존 경로) | ✅ |
| **FR-07** | E2E 수동 검증 시나리오 정의 (폴더 진입 체인) | Design §5 정의, 실행 이월 | ✅ 정의 |

---

## 9. 영향 범위 및 주의사항

### 9.1 DB 마이그레이션

| 항목 | 설명 |
|------|------|
| **필수 선행** | V053 배포 (wiki_folder_summaries_enabled=False라 코드만 배포 가능하지만, 테이블 필요) |
| **FK/COLLATE 규칙** | 명시 금지 (V037 선례), ENGINE=InnoDB만 지정 |
| **DDL COMMENT** | 전 컬럼+테이블 COMMENT 부여 (최초 적용 규칙) |
| **이전 데이터** | N/A (신규 테이블) |

### 9.2 배포 전략

| 단계 | 타이밍 | 조치 |
|------|--------|------|
| **1단계** | 코드 배포 | V053 선행 적용 + wiki_folder_summaries_enabled=False (기본값) |
| **2단계** | E2E 검증 (Qdrant/MySQL 기동 시) | Design §5 시나리오 5건 수동 실행 (공통 체크리스트) |
| **3단계** | 운영자 전환 | enabled=True로 설정 변경 + 모니터링 |

### 9.3 기존 기능 보호

| 기능 | 임계값 | 동작 |
|------|:---:|------|
| wiki-agentic-navigation (flat 목차) | 승인 문서 < 30 | 변화 없음 (폴더 모드 미활성) |
| wiki_read 도구 | - | 독립 동작 (wiki_list와 병렬) |
| 승인/편집 API | - | 지연 없음 (fire-and-forget) |

### 9.4 모니터링·관찰 항목

- `ai_tool_call` 로그에서 wiki_list 호출 추적 (tools 배선 확인)
- folder_summary_service warning 로그 모니터링 (LLM 증류 실패)
- wiki_folder_summary 테이블 행 수 증가 추적 (데이터 누적)
- 승인 API 응답 시간 (fire-and-forget이므로 +0 예상)

---

## 10. 이월 사항

| 항목 | 설명 | 담당 | 시점 |
|------|------|------|------|
| **V053 docs/wiki/ops 등재** | Migration Deploy Dependencies에 V053 추가 | 사용자 | `/wiki update` 명시 호출 시 |
| **FR-07 E2E 수동 검증** | Design §5 시나리오 5건 실행 (폴더 진입 체인) | QA/운영 | Qdrant/MySQL 기동 시 공통 체크리스트 일괄 |
| **후속 기능 기반 평가** | deep-wiki-research (병렬 fan-out), wiki-knowledge-promotion (중복 축적 사례 확인) | PM | 수요 실측 후 |

---

## 11. 핵심 성과 요약

### 11.1 기술적 성과

✅ **쓰기 시점 요약 계층** 완성 — 라우팅 검색 4부작의 설계 사상을 위키에 최초 적용
✅ **무회귀 점진 전환** — 기존 기능 0 영향, 운영자 선택적 활성화
✅ **계층 증류 RAPTOR 패턴** — 토큰 상한 안정 + 계층 구조 보존
✅ **폴더 단위 실패 격리** — 부분 실패에서도 부분 갱신 가능
✅ **Eventually Consistent 계약** — 요약은 힌트, 진실은 실시간 목록

### 11.2 운영 성과

✅ **프롬프트 크기 상수화** — 문서 수 증가와 무관 (∝ 폴더 수만, 상한 안정)
✅ **탐색 UX 개선** — "지도 → 구역 → 문서" 사람 같은 탐색 경험
✅ **관측 투명성** — wiki_list 호출이 ai_tool_call에 자동 기록, 결정 추적 가능
✅ **운영 부담 0** — API 지연 없음, 마이그레이션 자동화 가능 (기본 off)

### 11.3 아키텍처 진화

✅ **선행 기능 패턴 재사용** — WikiFeedbackService 팬아웃, WikiDistiller 구조 복제 → 코드 응집도 높음
✅ **정책 계층 강화** — expand_ancestors를 정책 계층으로 배치
✅ **DI 일관성** — optional 의존성으로 무회귀 조립 (agent-memory 관례 준수)
✅ **테스트 커버리지** — 43건 신규 + 회귀 4,024 건 green

---

## 12. Lessons Learned

### 학습 1: 설계-구현 갭은 "나쁜 설계"가 아닌 "설계의 선택사항"

G1 (list_children vs list_by_agent):
- 설계 작성 시 함수명을 미리 정했으나, 구현 시 context 변화 발생
- 에이전트당 폴더 수가 작다는 조건을 더 명확히 했으면 애초에 호출측 필터 선택
- **교훈**: 설계 단계에 "제약 조건의 크기"를 명시하면 구현 선택지가 좁혀짐

### 학습 2: 폴더 단위 실패 격리는 나중에 덧붙일 수 없다

G2 (failure isolation):
- 1차 구현에서 `_run_guarded`가 전체를 감싸니 한 폴더 실패 → 전체 중단
- Try/except를 폴더 루프 내로 이동 후에야 fix 가능
- **교훈**: fire-and-forget 패턴은 "반복 루프 내 격리"부터 설계

### 학습 3: 이중 주입 계약은 명시 단언이 필수

G3 (supervisor block injection):
- 코드상 같은 변수가 두 곳(supervisor/워커 prompt)에 사용되지만, 단언 테스트 없음
- **교훈**: "같은 변수니까 OK"라고 생각하는 계약은 시간이 지나면서 깨질 수 있음 → 명시 테스트 필수

### 학습 4: DDL COMMENT는 "나중에 채워야"가 아닌 "처음부터"

DDL 규칙 최초 적용 (D1):
- 기존 V050/V052는 비자명 컬럼만 COMMENT
- V053부터 전 컬럼 필수로 변경
- **교훈**: 스키마 자명성 규칙은 신규 테이블부터 적용하면 기술부채 최소화

---

## 13. 향후 진화 방향

### 13.1 즉시 후속 (필수 완료)

- **V053 배포** — 기능 코드 배포 선행 조건
- **E2E 수동 검증** — Qdrant/MySQL 기동 시 공통 체크리스트 일괄

### 13.2 중기 후속 (수요 실측 후)

1. **deep-wiki-research**: 폴더 계층을 기반으로 병렬 fan-out 종합 질의 (현재는 단일 경로)
2. **wiki-knowledge-promotion**: 에이전트 간 지식 승격 (중복 축적 사례 확인 시)
3. **위키 프론트엔드 UI**: 폴더 요약을 사용자에게 노출 (별도 후속)

### 13.3 장기 비전

- **hierarchical retrieval**: 폴더 계층을 기반으로 top-k 재순위 (현재는 flat 검색)
- **context-aware chunking**: 폴더 맥락을 청킹에 반영 (현재는 문서 단위)

---

## 14. 체크리스트 (배포 전)

- [ ] V053 마이그레이션 적용 (DB)
- [ ] 코드 배포 (wiki_folder_summaries_enabled=False 기본값)
- [ ] Design §5 E2E 시나리오 5건 수동 검증 (Qdrant/MySQL 기동)
- [ ] docs/wiki/ops에 V053 등재 (`/wiki update` 사용자 호출)
- [ ] 모니터링 대시보드 설정 (ai_tool_call, folder_summary_service 로그)
- [ ] enabled 전환 전 재점검 (회귀 테스트 재실행)

---

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 1.0 | 2026-07-25 | PDCA 완료 보고서 최종 — 설계 v0.2 as-built 정정 + 갭 4건 즉시 조치 (Match Rate 100%) | ✅ Completed |
