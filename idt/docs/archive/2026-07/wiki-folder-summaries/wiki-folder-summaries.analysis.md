# wiki-folder-summaries Gap Analysis

> **Date**: 2026-07-25
> **Design**: docs/02-design/features/wiki-folder-summaries.design.md (v0.2)
> **Analyzer**: gap-detector agent + 즉시 조치 반영
> **Match Rate**: **100%** (1차 96.7% → 갭 3건 즉시 해소)

---

## 1. 결과 요약

| 구분 | 판정 |
|------|------|
| 설계 항목 15건 (D1~D8, FR-01~FR-07) | 전건 구현됨 |
| 1차 Match Rate | 96.7% (14.5/15) |
| 즉시 조치 후 | **100%** |
| 신규 테스트 | 43건 (1차 41 + 조치 2) — 전부 green |
| 회귀 | 0 (실패 의심 전건 master 대조로 기존 문제 확정) |

## 2. 1차 발견 갭과 조치

| # | 갭 | 심각도 | 조치 |
|---|-----|:---:|------|
| G1 | 설계 D1의 `list_children` repo 메서드 미구현 (구현은 `list_by_agent`+호출측 prefix 필터) | 낮음(기능 동치) | **설계 as-built 정정(v0.2)** — 에이전트당 폴더 수가 작아(깊이≤3) 호출측 필터가 단순성 이득. 계약 문서/코드 일치화 |
| G2 | `_run_guarded`가 refresh 전체를 감싸 leaf 증류 실패 시 같은 배치의 조상 폴더 갱신 중단 (설계 D2는 폴더 단위 격리 문언) | 낮음 | **코드 보강** — `_refresh_one` 분리 + 폴더 루프 내 try/except (`folder_summary_service.py`), 검증 테스트 `test_leaf_failure_does_not_block_ancestors` 추가 |
| G3 | 폴더 모드에서 supervisor prompt 지도 블록 주입의 명시 단언 테스트 부재 (코드 경로는 동일 변수라 구조 보장) | 낮음 | **테스트 추가** — `test_folder_block_also_prepended_to_supervisor` (D1 이중 주입 계약 고정) |
| G4 | FAIL_TEXT 문구·`settings.wiki_model` 참조가 설계와 상이 | 없음 | 설계 v0.2에서 실제 값으로 정정 (구현이 더 정확 — 폴더 모드 문구 / 실존 설정) |

## 3. 구현이 설계를 넘어선 부분 (무해한 추가 — 채택 유지)

- 폴더 지도 헤더의 환각 방어 문장("지도만으로 답하지 말고…")
- 지도 max_bytes 절단 + "(전체 N개 중 M개 표시)" 고지
- `WikiPolicy.expand_ancestors` 도메인 배치 (서비스가 아닌 정책 계층)
- wiki_list path 정규화 `strip("/")` (LLM 입력 관용)
- `reject()`(draft→deprecated)도 재증류 트리거 — 승인 집합 무변화라 no-op성 여분 호출 (무해)

## 4. 검증 근거

- 위키 전체 스윕 251 passed (조치 반영 후), application+domain 광역 4,024 passed
- 회귀 판정 방법: 실패 의심 건마다 `git stash -u`로 master 대조 — 전건 기존 문제
  (langgraph add_node Mock inspect 9건 → 하니스 수정으로 부수 해결, 나머지는 환경성)
- SQL 계약: upsert ON DUPLICATE KEY UPDATE / list 필터·정렬을 컴파일 문자열로 고정

## 5. 비고 (갭 아님 — 이월/대기)

- `docs/wiki/ops/migration-deploy-deps.md`에 **V053 등재 필요** — 위키 갱신 규칙상
  사용자 `/wiki update` 명시 호출 대기
- FR-07 E2E 수동 실행 이월 — Qdrant/MySQL 기동 시 공통 체크리스트와 일괄
  (시나리오 5건은 Design §5에 정의 완료)
- 배포: V053 선행 적용 필수, `wiki_folder_summaries_enabled` 기본 off라 코드 선배포 안전
