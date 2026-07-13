# kb-management-ui Design-Implementation Gap Analysis

> **Analyzer**: bkit:gap-detector
> **Date**: 2026-07-10
> **Design**: `docs/02-design/features/kb-management-ui.design.md`

## 요약

| 항목 | 값 |
|------|-----|
| Match Rate | **96.9%** (31 / 32) — Check 내 즉시 해소 반영 (최초 판정 93.8%) |
| Match | 31 · Partial 0 · Missing 1 |
| 순수 Gap 개수 | 1 (Missing 1 — E2E 수동, 기지) |
| 핵심 Gap | ~~scope 라벨 불일치~~, ~~DetailPage ⑫⑬ 미커버~~ → **Check 내 해소**. 잔여: E2E 수동검증(기지) |
| 상태 | 설계-구현 일치 우수. 잔여는 수동 검증뿐 — report 진입 가능 |

## Check 내 즉시 해소 (2026-07-10)

| 최초 판정 | 조치 | 결과 |
|-----------|------|------|
| Gap 1 (§5.3 Partial): scope 배지 라벨 설계('전체공개') vs 코드('공개'), `KB_SCOPE_LABELS` dead code | 설계 §5.3을 "기존 `SCOPE_LABELS`(@/types/collection) 재사용"으로 정정(코드=진실 소스) + dead code 제거 | §5.3 → Match |
| Gap 2 (§6 Partial): DetailPage ⑫ disableClose·⑬ section_summary 뱃지 테스트 미커버 | 지연 응답 핸들러로 업로드 중 닫기 차단 테스트 + section_summary 킥오프 뱃지 테스트 추가 (DetailPage 4→6건) | §6 → Match |
| 참고 5: repo `save()` update 경로 kb_id 미반영 (실무 재현 없음 — document_id 매 업로드 UUID) | `existing.kb_id = metadata.kb_id` 1줄 반영 | 방어 보강 |

재검증: 프론트 KB 스위트 15건 + tsc 0 에러, 백엔드 repo 14건 통과
(간헐 ERROR 1건은 실행마다 다른 테스트로 이동 + 격리 실행 전건 통과 — 기지 Windows 이벤트루프 산발 이슈, 회귀 아님).

## 항목별 판정 (32항목)

### §3 결정사항 D1~D8 — 전건 Match

| ID | 근거 |
|----|------|
| D1 | V047 kb_id 컬럼+`idx_dm_kb`, `find_by_kb_id` created_at DESC + LIMIT/OFFSET |
| D2 | `unified_upload/use_case.py` `kb_id=request.extra_metadata.get("kb_id")` — 일반 업로드 None 불변 |
| D3 | `ListKbDocumentsUseCase`가 `KnowledgeBaseUseCase.get()` 선행 호출, 실패 시 repo 미호출(테스트 고정) |
| D4 | 라우터 description에 kb_id NULL 기존 문서 미표시 한계 명기 |
| D5 | `KnowledgeBaseInfo` 제자리 optional 확장 + 신규 `types/knowledgeBase.ts` |
| D6 | FormData + timeout 120s + 상태머신 + 저장 상태 카드, child_chunk_* 미노출 |
| D7 | AppSidebar `startsWith('/knowledge-bases')` 분기 |
| D8 | `canDelete = admin ∥ owner_id===userId`, 비소유자 미노출 테스트 |

### §4 백엔드 (6) · §5 프론트 (4) · §7 구현 순서 (7) — E2E 제외 전건 Match

### §6 테스트 (7파일)

| 파일 | 요구 | 실제 |
|------|:---:|:---:|
| test_list_documents_use_case.py | 6 | 6 |
| test_extra_metadata.py (kb_id) | 2 | 2 |
| test_document_metadata_repository.py (kb) | 4 | 4 |
| KnowledgeBasesPage.test.tsx | 6 | 6 |
| CreateKnowledgeBaseModal.test.tsx | 3 | 3 |
| KnowledgeBaseDetailPage.test.tsx | 4 | **6** (⑫⑬ Check 내 추가) |
| MSW handlers (5종) | 5 | 5 |

## Gap 목록

| # | Gap | 심각도 | 설명 |
|---|-----|:------:|------|
| ~~G1~~ | ~~scope 라벨 불일치 + dead code~~ | ~~경미~~ | Check 내 해소 (설계 정정 + KB_SCOPE_LABELS 제거) |
| ~~G2~~ | ~~DetailPage ⑫⑬ 미커버~~ | ~~경미~~ | Check 내 해소 (테스트 2건 추가) |
| G3 | E2E 수동 검증 미수행 | Low(기지) | KB 생성→업로드→agent-builder 드롭다운→검색 격리 실측. **kb-rag-filter G2와 묶어 일괄 실측 예정** (백엔드+Qdrant/ES 기동 필요) |

## 참고 (비차단, 기록만)

- CreateKnowledgeBaseModal scope 입력은 radio 그룹 (설계 표기 "Dropdown" — 기능 동일, CreateCollectionModal 선례와 일치하는 UX)
- 업로드 모달 상태머신 `idle/loading/done/error` — partial은 Qdrant/ES 저장 상태 행으로 표현 (설계 D6 의도 커버)

## 권고사항

1. **report 진입 가능**: 96.9% ≥ 90%, Act 불필요. `/pdca report kb-management-ui` 권장.
2. **배포 전 필수**: V047 DB 적용.
3. **G3**: E2E 실측 시 kb-rag-filter G2와 함께 체크리스트로 수행 — KB A/B 격리 검색 + Qdrant payload kb_id + 화면 흐름.
