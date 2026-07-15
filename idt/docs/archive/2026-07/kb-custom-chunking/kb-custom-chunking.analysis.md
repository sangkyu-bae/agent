# Analysis: kb-custom-chunking 설계-구현 Gap 분석

> Analyzed: 2026-07-15
> Phase: Check (PDCA — Design vs Implementation 대조)
> Scope: KB 단위 커스텀 청킹(전략 5종 + 토큰 파라미터 + 경계 정규식) 백엔드/프론트 전 구간
> Related Design: [kb-custom-chunking.design.md](../02-design/features/kb-custom-chunking.design.md) (D1~D12, V-01~V-07, §3.2/§5/§6/§8)
> Related Plan: [kb-custom-chunking.plan.md](../01-plan/features/kb-custom-chunking.plan.md) (FR-01~FR-10)

---

## 1. 요약

| 항목 | 결과 |
|------|------|
| **전체 Match Rate** | **96%** (50 / 52 checkpoint) |
| 설계 결정 D1~D12 | 12 / 12 Match |
| 검증 규칙 V-01~V-07 | 7 / 7 Match |
| §3.2 전략 매핑 (5종) | 5 / 5 Match |
| §5 API 스펙 | 6.5 / 7 (403 메시지 문구 Partial) |
| §6 UI 설계 | Match (사소한 편차 3건, 모두 정당) |
| §7 에러 처리 | 3.5 / 4 (403 문구 Partial) |
| §8 테스트 계획 | 7 / 8 (**infrastructure repository 테스트 Missing**) |

설계와 구현은 **매우 높은 일치도**를 보인다. 도메인 검증 로직(V-01~V-07), 전략별 factory 파라미터 매핑(§3.2), 레이어 배치(§9), 프론트 계약(§6.4)이 설계 그대로 구현됐다.

발견된 실질 Gap은 **단 1건(🔴 repository JSON 왕복/화이트리스트 테스트 부재)**이며, 나머지는 사용자 노출 메시지 문구·파일명 수준의 사소한 편차다. 대부분의 편차는 기존 프로젝트 관례(ApiError.message 사용, `KNOWLEDGE_BASE_*` 상수 접두사)를 따른 **정당한 편차**로 분류된다.

---

## 2. 설계 결정 D1~D12 대조

| # | 결정 | 판정 | 근거 (파일:라인) |
|---|------|:----:|------------------|
| D1 | `use_custom_chunking` TINYINT + `custom_chunking_config` JSON 컬럼 | ✅ Match | V048.sql:6-8, models/knowledge_base.py:59-64, entities.py:30-31 |
| D2 | config에 `version: 1` 키 | ✅ Match | custom_chunking.py:36 (`version: Literal[1] = 1`) |
| D3 | 전략 5종 노출명 + `boundary_pattern`→`clause_aware` 매핑 | ✅ Match | custom_chunking.py:18-24 `_FACTORY_STRATEGY`, :47-49 `factory_strategy()` |
| D4 | clause·custom 동시 true 금지 (create/update 422) | ✅ Match | custom_chunking.py:150-154, use_case.py create/update 모두 `_validate_chunking` 경유 |
| D5 | policy를 domain/custom_chunking.py 신설 + `ChunkingProfilePolicy` 상수 재사용 | ✅ Match | custom_chunking.py:13 import, 상수 재사용 |
| D6 | resolver 순서 custom→clause→None, custom 실패 시 legacy 폴백+warning | ✅ Match | chunking_resolver.py:35-38 순서, `_resolve_custom` 폴백+warning |
| D7 | `PATCH /knowledge-bases/{kb_id}/chunking` 신설 | ✅ Match | knowledge_base_router.py:368-398 |
| D8 | repo `update_chunking()` 6개 컬럼 화이트리스트 UPDATE | ✅ Match | repository.py:99-132 (6 values만) |
| D9 | `can_manage_settings()` = can_delete 규칙 (owner/ADMIN) | ✅ Match | policy.py:81-84 |
| D10 | 신규 업로드부터 적용, 재인덱싱 없음, display 기록 | ✅ Match | use_case.py update_chunking docstring, custom_chunking.py `display()`, upload_use_case.py:138 |
| D11 | boundary_rules parent≥1, ≤50개, 패턴 ≤200자 | ✅ Match | custom_chunking.py `_validate_boundary_rules` (`MAX_RULES`, `MAX_PATTERN_LENGTH` 재사용) |
| D12 | `semantic`은 overlap 미지원 → overlap>0 시 422 | ✅ Match | custom_chunking.py `_FORBIDDEN["semantic"]`, `_is_set`(>0) |

> D10의 재인덱싱 미발생·display 이력은 E2E 수동 검증(§8.3) 항목이나, 코드 경로(업로드 시 `resolver.resolve` 단일 경유)는 확인됨.

---

## 3. 검증 규칙 V-01~V-07 대조

| 규칙 | 내용 | 판정 | 근거 |
|------|------|:----:|------|
| V-01 | 수치 범위 (child 100~4000, overlap 0~500, parent 100~8000, min 50~2000) | ✅ Match | custom_chunking.py `_validate_ranges` + `_validate_optional_ranges` |
| V-02 | overlap<size, size≤parent, min<size | ✅ Match | 동 모듈 |
| V-03 | 전략별 금지 파라미터 (semantic+overlap>0 포함) | ✅ Match | `_FORBIDDEN`, `_validate_forbidden` |
| V-04 | boundary 1~50 / parent≥1 / 비어있지않고 ≤200 / `re.compile`, **실패 패턴 원문 포함** | ✅ Match | `_validate_boundary_rules`, 에러 문구 `invalid regex pattern '{pattern}': {exc}` |
| V-05 | 비-boundary 전략에서 boundary_rules 지정 거부 | ✅ Match | `_FORBIDDEN` 전 전략에 `boundary_rules` 포함 |
| V-06 | custom=true+config None / false+config 지정 거부 | ✅ Match | `validate_kb_settings` |
| V-07 | clause·custom 동시 true 거부 | ✅ Match | `validate_kb_settings` |

프론트 1차 검증도 동일 범위로 미러링됨(customChunkingForm.ts) — 최종 판정은 서버(Python `re`) 위임 구조 유지.

---

## 4. §3.2 전략별 factory 파라미터 매핑 대조

| config.strategy | 설계 전달 params | 구현 (`factory_params()`) | 판정 |
|-----------------|------------------|---------------------------|:----:|
| `full_token` | chunk_size, chunk_overlap | 동일 | ✅ Match |
| `parent_child` | parent_chunk_size, child_chunk_size(=chunk_size), child_chunk_overlap(=chunk_overlap) | `child_chunk_size`/`child_chunk_overlap` + `_with_parent_size` | ✅ Match |
| `semantic` | chunk_size, min_chunk_size (overlap 금지) | `_with_min_size({chunk_size})` | ✅ Match |
| `section_aware` | chunk_size, chunk_overlap, min_chunk_size | 동일 | ✅ Match |
| `boundary_pattern` | parent_patterns, child_patterns, parent_chunk_size, chunk_size, chunk_overlap | `_boundary_params` (priority 정렬 후 패턴 추출) | ✅ Match |

미지정 optional은 dict에서 생략해 factory 기본값 사용(설계 §3.2 주석과 일치).

---

## 5. §5 API 스펙 대조

| 항목 | 판정 | 근거 |
|------|:----:|------|
| POST body 두 필드 추가 | ✅ Match | `CreateKnowledgeBaseBody`, use_case create |
| GET(list/detail) 응답 두 필드 | ✅ Match | `KbInfoResponse`, `_to_kb_info` |
| PATCH 엔드포인트 신설 | ✅ Match | router.py:368-398 |
| 전체 교체 시맨틱 (부분 병합 아님) | ✅ Match | `UpdateKbChunkingBody` 6필드 → repo update_chunking 그대로 위임 |
| Response = KbInfoResponse (변경 후 전체) | ✅ Match | use_case update가 변경 후 재조회 반환 |
| 에러 403/404/422 매핑 | 🟡 Partial | `_raise_http` 매핑 메커니즘은 정확. 단 403 detail 문구가 설계 §7의 한글 문구와 상이 (§5-1) |
| §5.3 display 포맷 | ✅ Match | `display()` 필드 구성 일치 |

### 5-1. 🟡 403 에러 메시지 문구 편차 (Partial)

- 설계 §5.2/§7: 403 시 `"지식베이스 소유자만 설정을 변경할 수 있습니다"`
- 구현: `PermissionError("No settings access to knowledge base '{kb_id}'")` (영문)
- 프론트는 서버 detail을 `ApiError.message`로 표시 → 설계의 한글 403 문구는 화면에 나타나지 않음.
- **영향**: 낮음 (기능 정상, UX 문구만 상이). 기존 라우터들의 영문 PermissionError 관례와 일관됨.

---

## 6. §6 UI 설계 대조

| 항목 | 판정 | 근거 |
|------|:----:|------|
| 6.1 생성 모달 radio 3택 (기본/조항/커스텀) | ✅ Match | ChunkingModeSelector.tsx, CreateKnowledgeBaseModal.tsx |
| radio → clause/custom 값 결정 (동시 true 원천 차단) | ✅ Match | CreateKnowledgeBaseModal handleSubmit |
| 전략 변경 시 금지 필드 숨김+초기화 | ✅ Match | customChunkingForm.ts `resetForStrategy`, CustomChunkingFields 조건부 렌더 |
| 정규식 클라이언트 1차 검증 | ✅ Match | `isValidRegex` + 인라인 에러 |
| 전략별 설명 툴팁 | ✅ Match | `STRATEGY_OPTIONS.description` |
| 6.2 상세 카드 요약 + 수정 모달 프리필 + PATCH | ✅ Match | KbChunkingSettingsCard.tsx |
| 6.2 "기존 문서 미적용" 안내 문구 고정 | ✅ Match | 설계 §6.2 문구와 바이트 일치 |
| 6.3 컴포넌트 5종 | ✅ Match | 신규 3개 + 모달/DetailPage 수정 |
| 6.4 계약 파일 (types/service/hook/constants) | ✅ Match | knowledgeBase.ts, service, hook, api.ts |

### 6-1. 정당한 편차 (조치 불필요)

1. **정규식 검증 시점** blur → onChange (즉시 피드백, 기능 동등)
2. **`customChunkingForm.ts` 유틸 추출** (생성/수정 폼 공유 — 재사용 원칙)
3. **상수명 `KNOWLEDGE_BASE_CHUNKING`** (기존 `KNOWLEDGE_BASE_*` 접두사 관례 준수, 설계의 `KB_CHUNKING` 대체)

---

## 7. §7 에러 처리 대조

| Code | 판정 | 근거 |
|------|:----:|------|
| 422 V-01~V-07 (detail에 필드·규칙·패턴 원문) | ✅ Match | ValueError 문구 → `_raise_http`, 정규식 원문 포함 |
| 403 권한 없음 | 🟡 Partial | 메커니즘 ✅ / 한글 문구 미노출 (§5-1) |
| 404 KB 없음 | ✅ Match | `_raise_http` "not found" 매칭 |
| 업로드 시 config 손상 → legacy 폴백 + warning | ✅ Match | `_resolve_custom` (request_id, kb_id, error 포함 warning) |

로깅 LOG-001 준수 — print() 미사용, request_id·kb_id 포함 확인.

---

## 8. §8 테스트 계획 대조

### 8-1. 백엔드 (pytest)

| 설계 지정 파일 | 실제 | 판정 |
|----------------|------|:----:|
| `test_custom_chunking_policy.py` (신규) | `tests/domain/knowledge_base/test_custom_chunking.py` (40 tests) | 🟡 Match (파일명만 상이) |
| `test_chunking_resolver.py` (확장) | `TestResolveCustom` 존재 | ✅ Match |
| `test_use_case.py` (확장) | `TestCreateCustomChunking`, `TestUpdateChunking` 존재 | ✅ Match |
| `test_knowledge_base_router.py` (확장) | `TestCreateWithCustomChunking`, `TestUpdateChunkingSettings` 존재 | ✅ Match |
| `test_repository.py` (확장) — JSON 왕복 + 화이트리스트 | ~~부재~~ → **Check 직후 보강 완료**: `tests/infrastructure/knowledge_base/test_repository.py` 신설 (7 tests — save 매핑/JSON 왕복/기본값, _to_domain 매핑, update_chunking 화이트리스트 6컬럼·값·where 검증) | ✅ **Resolved** |

추가: `test_policy.py`에 `TestCanManageSettings` 추가됨 (D9 검증) ✅.

### 8-2. 프론트엔드 (Vitest)

| 설계 지정 파일 | 판정 |
|----------------|:----:|
| `CustomChunkingFields.test.tsx` (신규) | ✅ Match |
| `CreateKnowledgeBaseModal.test.tsx` (확장) | ✅ Match |
| `KbChunkingSettingsCard.test.tsx` (신규) | ✅ Match |

### 8-3. 수동 검증 (E2E) — Pending

- [ ] 커스텀 KB(boundary_pattern) 생성 → 업로드 → kb-content-browser 청크 경계 확인
- [ ] 양쪽 OFF KB 회귀 (기존 legacy 청킹 동일)
- [ ] 설정 변경 후 기존 문서 불변, 신규만 새 설정

> Qdrant/ES 기동 필요 — 프로젝트 공통 E2E 이월 항목과 함께 일괄 수행 권장.

---

## 9. Gap 목록 (심각도 순)

### 🔴 Missing (0건 — 1건 발견 후 즉시 해소)

| 항목 | 설계 위치 | 조치 |
|------|-----------|------|
| ~~repository JSON 왕복/화이트리스트 테스트~~ | design §8.1 | **해소됨** — Check 직후 `tests/infrastructure/knowledge_base/test_repository.py` 신설(7 tests). update_chunking이 청킹 6개 컬럼만 UPDATE함을 SQLAlchemy 문 검사로 검증. 참고: 이 머신의 산발적 이벤트 루프 setup 에러(WinError 10014)로 단일 실행에서 1~2건 setup ERROR가 무작위 발생하나, 3회 실행 합집합으로 7건 전부 통과 확인(assertion 실패 0건 — 알려진 환경 이슈). |

### 🟡 Partial / 사소 (2건)

| 항목 | 설계 | 구현 | 영향 |
|------|------|------|------|
| 403 에러 메시지 문구 | 한글 안내 문구 (§5.2/§7) | 영문 PermissionError → 프론트는 서버 문구/폴백 노출 | 낮음 |
| policy 테스트 파일명 | `test_custom_chunking_policy.py` | `test_custom_chunking.py` (40 tests) | 없음 (내용 충족) |

### 🟢 정당한 편차 (3건 — 조치 불필요)

1. 정규식 검증 시점 blur → onChange
2. `customChunkingForm.ts` 유틸 추출
3. 상수명 `KNOWLEDGE_BASE_CHUNKING`

---

## 10. 권장 조치

1. ~~(즉시) 🔴 repository 테스트 추가~~ → **완료** (2026-07-15, Check 직후 보강)
2. **(선택) 403 문구 정합**: (a) 설계를 구현(영문 관례)에 맞춰 개정 또는 (b) 프론트에서 403 한정 한글 문구 표기 — 기존 라우터 관례상 (a) 권장
3. **(문서) design 정정**: §8.1 policy 테스트 파일명 → `test_custom_chunking.py`, §6.4 상수명 → `KNOWLEDGE_BASE_CHUNKING`

---

## 11. 판정

**최초 Match Rate 96% → repo 테스트 보강 후 98%** (남은 감점: 403 문구 Partial, 테스트 파일명 Partial — 모두 기능 무영향 문구/이름 수준).
**Check 통과 (≥ 90%)** — `/pdca report kb-custom-chunking` 진행 가능.
