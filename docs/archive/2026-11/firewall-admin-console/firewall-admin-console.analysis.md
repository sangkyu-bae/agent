# firewall-admin-console Analysis Report

> **Analysis Type**: Gap Analysis (Design ↔ 구현) + 실행 검증
>
> **Project**: sangplusbot (idt + idt_front) — 연동: fireware, agent_mcp
> **Analyst**: 배상규
> **Date**: 2026-11-24
> **Design Doc**: [firewall-admin-console.design.md](firewall-admin-console.design.md) (v0.5)
> **Plan Doc**: [firewall-admin-console.plan.md](firewall-admin-console.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 방화벽 운영 조작이 curl·Grafana·작업함으로 흩어져 있고 수동 조작에 사용자 식별이 남지 않는다 |
| **WHO** | Agent Builder 관리자(admin 역할). 방화벽 에이전트의 `block_ip` 승인을 처리하는 사람과 같다 |
| **RISK** | 웹 화면이 차단 권한의 새 진입점이 된다. 토큰 노출·권한 우회·LIVE 모드 오조작을 서버에서 막아야 한다 |
| **SUCCESS** | dry-run 랩에서 화면으로 차단 → 목록 표시 → 해제까지 완료되고, fwctl 감사에 `actor=sangplusbot/admin:<user_id>`가 남는다. 설정 off면 메뉴·라우터가 없다 |
| **SCOPE** | M1 백엔드 fwctl 프록시 → M2 백엔드 Grafana 조회 → M3 프론트 현황·수동 조작 → M4 프론트 탐지·감사·승인 탭 → M5 연동 준비 절차·검증 |

---

## Strategic Alignment Check

PRD 문서는 없다(Plan에서 직접 시작). Plan의 문제 정의 기준으로 확인한다.

| 항목 | 기대 | 결과 |
|---|---|:---:|
| 핵심 문제 | 흩어진 방화벽 조작을 한 화면으로 모은다 | ✅ 현황·수동 조작·탐지·감사·승인이 `/admin/firewall` 한 화면에 있다 |
| 사용자 식별 | 수동 조작에 "누가"가 남는다 | ✅ 차단은 `actor`, 해제는 요청 ID(`adm-<user_id>-…`)로 남는다 |
| 안전장치 | 새 진입점이 안전장치를 우회하지 않는다 | ✅ admin 전용, 토큰은 서버에만, 화이트리스트·TTL·dry-run은 fwctl이 계속 강제 |
| 플랫폼 원칙 | 특화 기능을 코어에 하드코딩하지 않는다 | ✅ 기본 off, 조립 파일 1개, 코어 import 0건(AST 계약 테스트) |

### Success Criteria Status

| # | 기준 (Plan §4.1) | 상태 | 근거 |
|---|---|:---:|---|
| SC-1 | 설정 off에서 라우터 404, 메뉴 없음 | ✅ | `test_firewall_admin_wiring.py` + 실제 앱 로드(off 0경로/on 6경로) + 브라우저(꺼짐 상태 프론트 5176: 사이드바에 "보안 운영" 없음, 직접 진입 안내) |
| SC-2 | 일반 사용자 403, 무토큰 401 | ✅ | `test_admin_firewall_router.py::TestAuth` 7경로 × 3 |
| SC-3 | dry-run 왕복 | ✅ | 실측 테스트 `test_firewall_admin_live.py` + 브라우저(2026-11-23) |
| SC-4 | 감사에 `actor=sangplusbot/admin:<user_id>`, 감사 탭에 표시 | ✅ | fwctl 감사 파일 `adm-7-…` 행 + 감사 탭 "관리자 ID 7" |
| SC-5 | 화이트리스트·TTL 거부 전달 | ✅ | 브라우저 `172.28.10.10` → "보호 대상 주소" / TTL 99999 → 422 |
| SC-6 | LIVE 왕복·TTL 만료 | ✅ | 브라우저 LIVE 차단 → ipset 1건·LAB_BLOCK 13건 → 해제 버튼 → ipset 0건, 20초 차단 자동 만료(2026-11-24) |
| SC-7 | 탐지: 발화 룰·"이 IP 차단" | ✅ | attacker 가동 후 R01·R02·R04 발화, 버튼 → 현황 탭 초안·포커스 |
| SC-8 | 장애 분리 | ✅ | Grafana 중지: 현황 정상·탐지/감사만 안내 / fwctl 중지: "연결 안 됨"·폼 잠김 |
| SC-9 | 토큰 비노출 | ✅ | 빌드 산출물 토큰 검색 0건, 응답 본문 테스트 |
| SC-10 | 승인 탭 실건 | ✅ | 에이전트 `block_ip` 요청 → 승인 탭 표시 → 화면에서 승인 → 실행·감사 "에이전트" 기록 |

**Success Rate: 10/10**

### Decision Record Verification

| Source | Decision | Followed? | 비고 |
|---|---|:---:|---|
| [Plan] | 랩 + dry-run 기준, 실장비는 별도 | ✅ | 실장비 조건은 setup 문서 §7 |
| [Plan] | Agent Builder 관리자 메뉴, 떼어낼 수 있는 모듈 | ✅ | |
| [Plan] | idt → fwctl 직접 호출 | ✅ | |
| [Plan] | 관측은 Grafana API 경유 | ✅ | Viewer 토큰으로 3경로 실측 |
| [Plan] | 이력은 fwctl 감사만, DB 변경 없음 | ✅ | 마이그레이션 0건 |
| [Design] | Option C (조립 파일 + 순수 검증·LogQL + 서비스 2 + 클라이언트 2) | ✅ | |
| [Design] | 승인 API 무변경, 프론트 필터 | ✅ | |
| [Design] | 모드 전환 UI 없음 | ✅ | |

---

## 1. Analysis Overview

- **방법**: 정적 비교는 별도 에이전트가 Design v0.5와 코드를 항목별로 대조했다(앱·테스트 미실행, 모든 근거 file:line). 핵심 갭(G1·G2·G4·G5)은 직접 다시 확인했고, G1은 실제 응답으로 재현했다. 실행 검증은 Do 단계(module-1~5)에서 수행한 결과를 쓴다.
- **범위**: worktree `../wt/firewall-admin-console`, 변경 35파일(백엔드 19, 프론트 14, 문서 2 + 수정 파일).

---

## 2. Gap Analysis

### 2.1 점수

| 축 | 점수 | 산정 |
|---|---:|---|
| Structural | 97 | 파일·엔드포인트·환경변수·컴포넌트 72.5/75 (프론트 테스트 파일 구성 상이, `StatusBadge` 대신 `ui/Badge`) |
| Functional | 98 | Page UI Checklist 41.5/42 + Plan FR 23.5/24 |
| API Contract | 95 | 7개 엔드포인트 × (요청·응답·오류) 21항목 중 20항목 일치 |
| Runtime | 100 | Design §8.4 L3 시나리오 8/8 통과, 실측 테스트 5/5, 단위·라우터 232건, 프론트 74건 |

```
Overall = 97×0.15 + 98×0.25 + 95×0.25 + 100×0.35 = 97.8%
```

### 2.2 Gap 목록 (Critical 0 / Important 0 / Minor 9)

| ID | 영역 | 내용 | 근거 | 제안 |
|---|---|---|---|---|
| G1 | API 오류 형식 | 형이 틀린 입력(`ttl_seconds:"600"`, `reason:5`, `limit=abc`)은 Pydantic이 먼저 막아 `{"detail":[...]}` 목록 형식 422가 나간다. `code`·`request_id`가 없다. 화면은 사전 검증으로 이 경로를 타지 않는다 | `schemas/firewall_admin.py:24-29`, `admin_firewall_router.py`의 `limit: int` — 실제 응답으로 재현 | 라우터 전용 검증 오류 변환으로 `INVALID_TTL`·`INVALID_REASON`·`INVALID_FILTER` 코드를 붙인다 |
| G2 | 탐지 탭 | "차단 중" 표시가 발화·대기 인스턴스에만 나온다. 과거 출발지가 지금 차단 중이어도 표시되지 않는다 | `FirewallDetectionTab.tsx:208-214` | 비활성 인스턴스도 차단 중이면 배지만 표시 |
| G3 | 기동 로그 | 미설정 warning을 남긴 경우에도 `firewall_admin enabled` info를 남긴다(§6.3과 다름) | `firewall_admin_di.py:58-62` | Design §6.3 문구를 실제 동작으로 고친다 |
| G4 | 오류 문구 | 백엔드 `GRAFANA_UNAVAILABLE` 기본 메시지가 옛 문구("탐지 정보를…")다. 화면은 프론트 문구를 써서 영향 없음 | `errors.py:77-80` | 백엔드 문구를 프론트와 맞춘다 |
| G5 | 폴링 범위 | 상단 메뉴가 모든 관리자 화면에서 status를 30초마다 조회하고, 그때마다 fwctl `/healthz`를 부른다. fwctl이 내려가 있으면 warning이 30초마다 쌓인다 | `useAdminNavGroups.ts:14`, `useFirewall.ts:44-45`, `fwctl_client.py:86` | 메뉴용 조회는 폴링하지 않고, health 실패 로그를 debug로 낮춘다 |
| G6 | 상수 중복 | `IPV4_RE`가 두 컴포넌트에 각각 있다 | `BlockIpForm.tsx:20`, `FirewallAuditTab.tsx:56` | `types/firewall.ts`로 모은다 |
| G7 | 페이지 간 import | 승인 탭이 `pages/JobsPage/RejectReasonDialog`를 직접 import한다 | `FirewallApprovalsTab.tsx:14` | 이번 범위에서는 Design에 결합을 기록 |
| G8 | 출처 주석 | 훅·서비스·타입 파일의 출처 주석이 `Design Ref:` 형식이 아니다 | `useFirewall.ts:23` 외 2 | 형식 통일 |
| G9 | Plan FR-21 | 룰 인스턴스의 사유 초안에 건수가 없다(v0.4 결정). Plan 문구와 Version History에 명시되지 않았다 | `FirewallDetectionTab.tsx:53` | Version History에 기록 |

### 2.3 Page UI Checklist (§5.4)

| 화면 | 항목 | 구현 | 부분 | 누락 |
|---|:---:|:---:|:---:|:---:|
| 공통 | 8 | 8 | 0 | 0 |
| 현황 탭 | 12 | 12 | 0 | 0 |
| 탐지 탭 | 10 | 9 | 1 (G2) | 0 |
| 감사 탭 | 6 | 6 | 0 | 0 |
| 승인 탭 | 6 | 6 | 0 | 0 |

### 2.4 Plan FR

FR-01~24 중 23건 구현, FR-21 부분(G9 — Design 결정에 따른 문구 차이).

### 2.5 규칙·구조

- import 경계(§9.3): 준수. AST 계약 테스트(`test_firewall_admin_isolation.py`)로 고정.
- `main.py` 변경: import 1줄 + wire 1줄 + close 1줄.
- 프론트 상수는 `types/firewall.ts`, 쿼리 키는 `lib/queryKeys.ts`만 사용. 뮤테이션 버튼은 `LoadingButton`/`Button isPending`.

### 2.6 문서 표류 (14건)

Design 본문이 코드나 자기 Version History와 다른 곳이다. 코드가 맞고 문서를 고친다.

| ID | 위치 | 내용 |
|---|---|---|
| D1 | §6.1·§5.4 | `GRAFANA_UNAVAILABLE` 문구가 옛 문구 |
| D2 | §2.2·§8.2 | 함수명 `validate_audit_filters` → 실제 `validate_audit_query` |
| D3 | §10.1 | 쿼리 키 접두가 `['admin','firewall',…]` |
| D4 | §4.5 | LogQL 함수는 검증된 쿼리 객체 1개를 받는다 |
| D5 | §3.1 | 모델·뷰 객체 추가분 미기재 |
| D6 | §11.1 | 프론트 테스트 파일 구성(`index.test`·`tabs.test`·`AdminNavFirewall.test`) |
| D7 | §11.1 | `useAdminNavGroups.ts` 미기재, `AdminSectionTabs`는 수정하지 않음 |
| D8 | §5.3 | `StatusBadge` → `ui/Badge`, 훅 목록 누락 |
| D9 | §6.3 | 기동 info 로그 조건(G3) |
| D10 | §7 | "Settings 마스킹 확인" 전제가 없음 — 토큰을 로그하지 않는 방식 |
| D11 | 머리말·체크박스·이력 순서 | Status Draft, 체크박스 미표시, 이력 순서 뒤섞임 |
| D12 | §4.2 | audit `actor`에 영숫자 1자 이상 조건 추가(`.*` 거부) |
| D13 | Plan FR-21 | 사유 초안 형식(G9) |
| D14 | Plan M5 | `docs/SOURCE-OF-TRUTH.md` 반영 여부가 사용자 확인 대기 |

---

## 3. 실행 검증 요약 (Do 단계 수행)

| 수준 | 대상 | 결과 |
|---|---|---|
| L0 백엔드 | domain·application·infrastructure·router·조립·격리 계약 | 232건 통과 |
| L1 실측 | 실제 fwctl·Grafana 왕복 | 5건 통과 |
| L2 프론트 | 훅·메뉴·페이지·탭 | 74건 통과 |
| L3 E2E | Design §8.4 시나리오 1~8 | 8/8 통과(브라우저) |
| 회귀 | 백엔드 전체 | 신규 실패 0건(상시 실패 55건, master와 동일) |
| 회귀 | 프론트 전체 | 신규 실패 0건(상시 실패 10건) |
| 정적 | `tsc -b` / 변경 파일 린트 | 신규 0건 / 0건 |

실행 검증 중 찾아 고친 결함(Do 단계 반영 완료): 이전 결과 안내 잔존, 과거 출발지 차단 버튼, 의미 없는 측정값 표시, 감사 탭 캐시, 승인 응답 시간 초과 시 오류 오표시.

---

## 4. 기존 결함 (이번 변경 범위 밖, 미수정)

| 항목 | 내용 |
|---|---|
| 승인 API 응답 지연 | `POST /approvals/{id}/approve`가 에이전트 재개까지 기다려 30초를 넘길 수 있다. 작업함 화면은 이 경우 오류로 표시한다 |
| 승인 필요 도구의 `action` 카테고리 | 본문 인자가 없는 도구에 `action`을 지정하면 워커가 실행에서 빠지고, 에이전트가 호출하지 않은 도구를 호출했다고 답한다 |
| 경계 계약 테스트 | `pii_masking/test_boundary_contract.py` 1건이 master에서도 실패 |

---

## 5. 결론

Match Rate **97.8%**, 성공 기준 10/10, Critical·Important 갭 0건. Minor 9건과 문서 표류 14건이 남아 있었다. 코드 수정이 의미 있는 것은 G1(오류 형식)·G4(백엔드 문구)·G5(폴링 범위)·G6(상수 중복)이고, 나머지는 문서 정리로 해소된다.

---

## 6. 조치 결과 (2026-11-24, 사용자 선택: 코드 4건 + 문서 정리)

| ID | 조치 | 검증 |
|---|---|---|
| G1 | 라우터 전용 `route_class`가 FastAPI 검증 오류를 같은 형식으로 변환(`INVALID_IP`·`INVALID_TTL`·`INVALID_REASON`·`INVALID_FILTER`, 그 밖은 신규 `INVALID_REQUEST`). 앱 전역 처리는 무변경 | 라우터 테스트 9건 추가(형 오류 6, 비JSON 1, `limit=abc` 2) + 무토큰이면 여전히 401 |
| G4 | 백엔드 `GRAFANA_UNAVAILABLE` 문구를 프론트와 통일 | 단위 테스트 |
| G5 | 메뉴용 status 조회는 `poll:false`(방화벽 페이지만 30초 갱신), fwctl health 실패 로그를 debug로 | 훅 테스트(관찰자별 `refetchInterval`), fwctl 클라이언트 테스트(warning 미발생) |
| G6 | `FIREWALL_IPV4_RE`를 `types/firewall.ts`로 공용화. 감사 수행자 필터도 서버 규칙(영숫자 1자 이상)과 맞춤(D12) | 탭 테스트 1건 추가(`.*` 거부) |
| G2·G3·G7·G8·G9, D1~D13 | Design v0.6에 반영(동작 설명·함수명·쿼리 키·파일 구성·기동 로그·토큰 로그·결합 기록·FR-21 초안 형식, 체크리스트 완료 표시, 이력 정렬). Plan FR-21에 주석 | — |
| D14 | `docs/SOURCE-OF-TRUTH.md` 반영은 사용자 확인 대기로 남김 | — |

조치 후 테스트: 백엔드 방화벽 모듈·계약 248건, 실측 5건, 프론트 관련 98건 통과. `tsc -b` 신규 오류 0건, 변경 파일 린트 0건.

조치 후 재산정: 코드 갭 G1·G4·G5·G6 해소, 문서 갭 G2·G3·G7·G8·G9 해소(Design이 의도된 동작을 기술). 남은 갭 0건(D14는 사용자 결정 사항).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-24 | 최초 분석. 정적 비교(별도 에이전트) + Do 단계 실행 검증 결과 통합 | 배상규 |
