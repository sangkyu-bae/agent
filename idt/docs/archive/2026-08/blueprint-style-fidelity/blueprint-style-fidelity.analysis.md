# blueprint-style-fidelity Gap Analysis

> **Feature**: blueprint-style-fidelity
> **Date**: 2026-08-23
> **Plan**: [blueprint-style-fidelity.plan.md](../01-plan/features/blueprint-style-fidelity.plan.md) v0.1
> **Design**: [blueprint-style-fidelity.design.md](../02-design/features/blueprint-style-fidelity.design.md) v0.1 (Option C)
> **Method**: gap-detector 정적 분석 + 런타임 검증(pytest 211건, 골든 회귀 8건, 라우터 L1 21건, 프론트 tsc)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 블루프린트 추출이 폰트·좌표·도형·푸터 정보를 버려서 산출 PPT가 샘플 스타일과 무관해 보인다 |
| **WHO** | P2 KB 운영자/에이전트 소유자, PPT 수신 사용자 |
| **RISK** | schema v2 전환 시 기존 레코드·프론트 PUT 라운드트립 호환 |
| **SUCCESS** | SC-1~8 — 골든 회귀 테스트로 자동 검증 |
| **SCOPE** | module-1 schema → 2 extract → 3 render → 4 migrate (4/4 완료) |

---

## Strategic Alignment Check

### Plan Alignment

| 항목 | 결과 |
|------|------|
| 핵심 문제(WHY) 해결 | ✅ 원인 6건 중 1~5 해소. 실 DB 레코드 `3bac89cb…` 재추출 후 실 비전 LLM 결과에서도 폰트·로고·푸터·장식·크기 계층 보존 확인 |
| 사용자 결정 반영 | ✅ 폰트 패스스루(DR-3) / 같은 id 재추출(DR-6) / 범위 1~5 |
| 아키텍처 결정(Option C) | ✅ 정책 2개·VO 1개·렌더 단계 추가·UseCase+CLI — 설계대로 |

### Success Criteria Status

| SC | 기준 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 모든 run 폰트 = Malgun Gothic | ✅ Met | `test_sc1_all_runs_use_original_malgun_gothic`; DB `font_mapping` identity |
| SC-2 | 로고 본문 (0.83,0.04) / 표지 (0.06,0.07) | ✅ Met | `test_sc2_logo_positions_cover_vs_body`; DB `asset.box`/`cover_box` |
| SC-3 | 슬라이드당 페이지번호 1개, 우하단 | ✅ Met | `test_sc3_exactly_one_page_number_bottom_right_per_body_slide` |
| SC-4 | 원본 푸터 텍스트·캡션·#666666 | ✅ Met | `test_sc4_original_footer_text_with_caption_style` |
| SC-5 | 푸터 띠 + section_lead 카드 | ✅ Met | `test_sc5_footer_band_and_cards_rendered` (실제 색 `#F3F4F6`) |
| SC-6 | toc `1.` 16pt, 제목 24pt bold primary | ✅ Met | `test_sc6_toc_numbered_16pt_and_title_24pt_primary` |
| SC-7 | accent1 `#E07A1F`, primary `#1F3A5F` | ✅ Met | `test_sc7_palette` |
| SC-8 | v1 픽스처 로드·렌더 | ✅ Met | `test_sc8_v1_snapshot_renders_without_decorations` + 직렬화 v1 폴백 3건 |

**8/8 Met.**

### Decision Record Verification

| DR | 결과 | 비고 |
|----|:----:|------|
| DR-1 장식 = `decorations` 별도 튜플 | Followed | `schemas.py` 신뢰 경계 테스트가 `decorations`를 서버 계산 필드로 고정 |
| DR-2 footer 슬롯 유지 + 생성 프롬프트에서만 제외 | Followed | 프롬프트·SlotContentPolicy·렌더러 3중 차단 |
| DR-3 폰트 패스스루 | Followed | |
| DR-4 REQUIRED 4키 + 옵션 2키 | Followed | 프론트 `OPTIONAL_SIZE_KEYS` 미러 |
| DR-5 로드 시 버전 보존, 쓰기 시 승격 | Followed | `update()`/`reextract()` 에서만 2 |
| DR-6 UseCase + CLI | Followed | `build_admin_use_case()` 헬퍼 추가 (정당) |
| DR-7 `align`만 LLM Draft | Followed | |
| DR-8 차트 막대 제외 = IoU + 얇은 도형 | **Deviated (정당)** | 실데이터: `find_tables`가 카드를 표로 오탐 → 비전 슬롯 포함율 ≥0.8 + CHART 슬롯 보유 패턴에만 막대 규칙. 테스트로 고정 |

---

## 1. Analysis Overview

### 1.1 Purpose
Design v0.1 대비 구현 충실도 측정, 실데이터로 보정된 설계 편차의 정당성 판정, 남은 갭 식별.

### 1.2 Scope
`src/{domain,application,infrastructure}/blueprint`, `src/interfaces/schemas/blueprint.py`, `src/api/blueprint_di.py`, `scripts/blueprint_reextract.py`, `idt_front/src/types/blueprint.ts`, 테스트 7개 디렉토리.

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints
엔드포인트 추가/변경 없음 (설계 §4 일치). 페이로드만 v2 확장.

### 2.2 Data Model (§3.1)

| 설계 항목 | 구현 | 상태 |
|-----------|------|:----:|
| `Decoration`, `Align`, `Slot.align`, `PagePattern.decorations`, `HeaderFooter(+3)`, `StyleTokens.common_decorations` + `size()`, `BlueprintAsset.cover_box`, `CURRENT_SCHEMA_VERSION` | `value_objects.py` | ✅ 9/9 |
| `fills → (hex, area, box)` | `PageStats.rects: tuple[FillRect,…]` 별도 필드 | ⚠️ 편차 #1 (정당 — `dict(fills)` 소비처 보존) |
| `_migrate_v1()` 함수 | 필드별 `.get()` 기본값 | ⚠️ 편차 (동작 동일, 문서 수정) |

### 2.3 Component Structure (§9.1)
36.5 / 38 존재. 누락: `golden_patterns.json` 픽스처 (`GoldenAdapter`가 `golden_v1.json`에서 파생 — 단일 픽스처가 더 안전, 문서 수정), `_migrate_v1` 명명.

### 2.4 Functional Depth (FR-01~12)

| FR | 상태 | 비고 |
|----|:----:|------|
| FR-01 ~ FR-07 | ✅ Full | |
| FR-08 toc / 카드 소제목 | ⚠️ Partial | toc ✅. **카드 소제목 h3 bold 미구현** — bullets 슬롯이 평문 리스트라 소제목/본문 쌍 표현 불가 (G1) |
| FR-09 ~ FR-12 | ✅ Full | FR-09 위험완화(표지 title만 신뢰)는 미적용 (G7) |
| Plan B-5 표 합계행 bold·셀 여백 | ❌ | FR 번호 없이 스코프에만 있음 (G3) |

### 2.5 Page UI Checklist
N/A (백엔드 전용).

### 2.6 API Contract Verification (§4.1 3-way)
`SlotSchema.align` / `DecorationSchema` / `PatternSchema.decorations` / `HeaderFooterSchema` 3필드 / `StyleSchema.common_decorations` / `AssetSchema.cover_box` / `schema_version=2` — **7/7 PASS** (pydantic ↔ `blueprint.ts`). 프론트 편집기는 spread 패치라 라운드트립 보존 (`BlueprintTabs.tsx:105,246`), `test_v2_fields_roundtrip_through_payload_and_response`로 고정.

시그니처: `reextract` / `FooterPolicy.apply` / `DecorationPolicy.apply` / `StyleTokens.size` / 렌더러 4함수 / CLI — 일치. `Repository.replace` 파라미터명 `assets`→`asset_bytes` 드리프트 (G10).

### 2.7 Runtime Verification Results

| 레벨 | 실행 | 결과 |
|------|------|------|
| pytest (domain/application/infrastructure/integration/interfaces/api/db) | 211건 | **211 passed** (타이밍 플레이크 1건 수정: `updated_at >= created_at`) |
| 골든 회귀 SC-1~8 | `test_golden_sample_fidelity.py` | 8/8 |
| L1 라우터 (TestClient) | `test_admin_blueprint_router.py` + interface v2 | 21 passed |
| 프론트 타입 | `tsc --noEmit` | exit 0 |
| 실 DB 재추출 | `scripts/blueprint_reextract.py` (실 비전 LLM) | 성공 — v2, 장식·푸터·폰트·좌표 모두 기대값 |
| L1 라이브 서버 | `GET /api/v1/admin/blueprints/3bac89cb…` | ⚠️ **422 `unsupported blueprint schema_version 2`** — 포트 8000을 잡은 프로세스가 20:27에 시스템 Python으로 띄운 구버전 uvicorn(PID 4104/5300, 리로드 안 됨). venv 인스턴스(16900)는 포트 충돌로 서비스 불가. **서버 재시작 필요** — 재시작 전까지 이 블루프린트로 PPT 생성 불가 |

Runtime score: 100 (테스트 기준). 라이브 서버 이슈는 코드 갭이 아닌 운영 항목으로 별도 기록.

### 2.8 Match Rate Summary

| 축 | 점수 | 가중 |
|----|:----:|:----:|
| Structural | 96% | 0.15 |
| Functional | 94% | 0.25 |
| Contract | 98% | 0.25 |
| Runtime | 100% | 0.35 |
| **Overall** | **97%** | |

(정적 전용 gap-detector 공식: 94%)

---

## 3. Code Quality Analysis

| 항목 | 결과 |
|------|------|
| 플레이스홀더 (TODO/FIXME/NotImplementedError/print) | 없음 |
| 함수 40줄 | 위반 1: `blueprint_di.wire_blueprint` 50줄 (기존 46줄 + 3줄, 이번 변경 전부터 초과) |
| 복잡도 C901 ≤10 | 통과 |
| ruff | 변경 범위 clean |
| 레이어 계약 | `test_layer_contract.py` 통과 — domain에 PyMuPDF/python-pptx 없음 |
| Repository commit 금지 | `test_repository_never_commits` 통과, CLI가 트랜잭션 경계 보유 |

---

## 5. Test Coverage

신규/수정 테스트: domain 21, application 6, infrastructure 14, interfaces 4, integration 8. SC 8개 모두 전용 테스트 보유. 미커버: 라우터 HTTP 레벨 v2 PUT (pydantic 레이어만, G6), 공통 장식 상한 경고 (G2).

---

## 6. Clean Architecture Compliance
위반 없음. 정책은 domain 순수 함수, 렌더·추출은 infrastructure, 조립은 application. 점수 100.

---

## 7. Gap List

| ID | 심각도 | 신뢰 | 갭 | 조치 |
|:--:|:--:|:--:|----|------|
| G1 | **Important** | 95% | FR-08 후반 — section_lead 카드 소제목 h3 bold primary 미구현 (bullets 평문) | Plan에서 공식 descope + 후속 티켓(권장) 또는 `_bullets`에 section_lead 첫 항목 h3 bold 분기 |
| G2 | Minor | 95% | `common_decorations` 상한(4) 초과 시 경고 없음 (패턴별은 있음) | 경고 1줄 + 테스트 |
| G3 | Minor | 90% | Plan B-5 표 합계행 bold·셀 여백 미구현 | Plan §2.2로 descope 또는 `_table` 보강 |
| G4 | Minor(doc) | 95% | `golden_patterns.json` 픽스처 없음 — `golden_v1.json`에서 파생 | Design §8.5 수정 |
| G5 | Minor(doc) | 90% | `_migrate_v1` 명명 | Design §3.4 수정 |
| G6 | Minor | 85% | 라우터 HTTP 레벨 v2 PUT 테스트 없음 | 라우터 테스트 1건 추가 |
| G7 | Minor | 85% | align 위험완화(표지 title만 신뢰) 미적용 | `_pattern_from_draft` 좁히기 또는 Design에 Literal 검증 충분 기록 |
| G8 | Minor(doc) | 95% | Plan FR-08 "subtitle"→ 실제 `h3`(SC-6 16pt) | Plan 수정 |
| G9 | Minor(risk) | 70% | 장식 면적·bg 임계 완화 → 다른 샘플에서 잡음 유입 가능 | 2번째 샘플 온보딩 시 재점검 |
| G10 | Minor | 90% | `replace(assets)` → `asset_bytes` 파라미터명 | rename |
| **OPS-1** | **Important** | 100% | 라이브 서버가 구버전(시스템 Python uvicorn) — DB는 v2라 422 | venv uvicorn 단독 재시작 (`.venv/Scripts/python -m uvicorn src.api.main:app --reload --port 8000`), 포트 점유 프로세스 4104 종료 |

Critical 없음.

### 설계 편차 정당성

| # | 편차 | 판정 |
|:-:|------|:----:|
| 1 | `PageStats.rects` 추가 | 정당 |
| 2 | DecorationPolicy 임계(bg 12, 포함율 0.8, 비전 슬롯만, CHART 게이트, 면적 0.001) | 정당 — SC-5를 만족시키는 최소 변경, 각각 테스트 고정 |
| 3 | subtitle 규칙 (h2~body 구간 2개 이상) | 정당 — **설계 §3.3 원문 규칙은 자기 기대값(subtitle 18, h3 16)과 모순**, 코드가 기대값을 실현. Design 수정 필요 |
| 4 | `build_admin_use_case()` | 정당 — §4.4 "blueprint_di로 조립" |
| 5 | FR-08 카드 소제목 미구현 | **갭 (G1)** |
| 6 | `_widen()` 푸터 박스 | 정당 — 글자 bbox 그대로면 클립 |

---

## 8. Overall Score

**97% (런타임 포함) / 94% (정적)** — 90% 기준 통과. Critical 0, Important 2 (G1 기능 descope 결정, OPS-1 서버 재시작).

## 9. Act 반영 (2026-08-23, Checkpoint 5 결정: "Minor 수정 + G1 descope")

| ID | 조치 | 결과 |
|----|------|------|
| G1 | Plan v0.2 에서 카드 소제목 공식 descope + Out of Scope 기록 | 문서 |
| G2 | `DecorationPolicy._common` 상한 초과 경고 + `test_decoration_policy_common_cap_emits_warning` | 코드 |
| G3 | Plan v0.2 B-5 descope | 문서 |
| G4/G5/G8 | Design §8.5·§3.4, Plan FR-08 정정 | 문서 |
| G6 | `test_update_v2_payload_with_decorations_roundtrips_over_http` (라우터 HTTP 레벨) | 테스트 |
| G7 | `_pattern_from_draft`: 표지 title 만 LLM align 신뢰 (Design DR-9) + 테스트 | 코드 |
| G10 | `replace(assets)` 파라미터명 정정 | 코드 |
| §3.3 | Design v0.2 subtitle 규칙·DecorationPolicy 임계·DR-8 실데이터 정정 | 문서 |
| OPS-1 | 사용자가 직접 서버 재시작 예정 | 운영 |

Act 후 테스트: 197 passed (blueprint suite), ruff clean. 잔여 갭: G9(위험 메모) 만. **Match Rate 97% 유지 → report 단계 진행 가능.**
