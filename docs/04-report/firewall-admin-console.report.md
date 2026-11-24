# firewall-admin-console Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front) — 연동: fireware, agent_mcp
> **Author**: 배상규
> **Completion Date**: 2026-11-24
> **PDCA Cycle**: Plan → Design → Do(module-1~5) → Check(1회, 조치 반영)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | firewall-admin-console — fireware 방화벽 관리 화면 (Agent Builder 관리자 메뉴 "보안 운영 > 방화벽") |
| Start Date | 2026-11-23 |
| End Date | 2026-11-24 |
| Duration | 2일 |
| Workspace | worktree `../wt/firewall-admin-console`, 브랜치 `feature/firewall-admin-console` (미커밋) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 97.8%   Success Criteria: 10/10 │
├─────────────────────────────────────────────┤
│  ✅ Complete:     24 / 24 FR (FR-21 문구 조정) │
│  ⏳ Carried:       1 item (SOURCE-OF-TRUTH 반영) │
│  ❌ Cancelled:     0                          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 방화벽 차단 조회·조작은 curl, 탐지 알림·감사는 Grafana, 에이전트의 `block_ip` 승인은 작업함에서 따로 처리해야 했고, 수동 조작에는 "누가 했는지"가 남지 않았다. |
| **Solution** | idt 백엔드에 기본 off인 `firewall_admin` 모듈(엔드포인트 7개, 조립 파일 1개)을 두고 fwctl과 Grafana를 대신 호출한다. 관리자 화면 `/admin/firewall`에 상태 띠와 탭 4개(현황·탐지·감사·승인)를 만들었다. 토큰은 서버에만 있고, 수동 조작의 수행자는 서버가 `sangplusbot/admin:<user_id>`로 채운다. |
| **Function/UX Effect** | 한 화면에서 DRY-RUN/LIVE 모드 확인, TTL 차단·해제, 발화 중인 탐지 룰 8개 확인, 탐지 행에서 차단 폼 초안 채우기, 최근 7일 감사 조회, 에이전트 차단 요청 승인까지 처리한다. 실제 랩에서 LIVE 차단 → ipset 반영 → 해제, 에이전트 요청 → 화면 승인 → 실행까지 확인했다. |
| **Core Value** | 탐지 → 판단 → 승인 → 차단 → 감사 흐름을 사람이 한곳에서 감독하고, 모든 조작이 수행자와 함께 fwctl 감사에 남는다. 화면은 fwctl 계약만 바라보므로 집행부를 실장비용으로 바꿔도 그대로 쓴다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 설정 off면 라우터 404, 메뉴 없음 | ✅ Met | `test_firewall_admin_wiring.py`, 실제 앱 로드(off 0경로 / on 6경로), 브라우저(꺼짐 상태 프론트: 사이드바에 없음·직접 진입 안내) |
| SC-2 | 일반 사용자 403, 무토큰 401 | ✅ Met | `test_admin_firewall_router.py::TestAuth` 7경로 × 3 |
| SC-3 | dry-run 왕복 | ✅ Met | 실측 테스트 `test_firewall_admin_live.py`, 브라우저 차단 → "실제로 차단되지 않았습니다(DRY-RUN)" |
| SC-4 | 감사에 `actor=sangplusbot/admin:<id>`, 감사 탭 표시 | ✅ Met | fwctl `audit.ndjson`의 `adm-7-…` 행, 감사 탭 "관리자 ID 7" |
| SC-5 | 화이트리스트·TTL 거부 전달 | ✅ Met | 브라우저 `172.28.10.10` → "보호 대상 주소", TTL 99999 → `INVALID_TTL` |
| SC-6 | LIVE 왕복·TTL 만료 | ✅ Met | LIVE 차단 → ipset 1건·LAB_BLOCK 로그 → 해제 버튼 → ipset 0건, 20초 차단 자동 만료 |
| SC-7 | 탐지 발화·"이 IP 차단" | ✅ Met | attacker 가동 후 R01·R02·R04 발화, 버튼 → 현황 탭 초안·포커스 |
| SC-8 | 장애 분리 | ✅ Met | Grafana 중지: 현황 정상·탐지/감사만 안내 / fwctl 중지: "연결 안 됨"·폼 잠김 |
| SC-9 | 토큰 비노출 | ✅ Met | 빌드 산출물 토큰 검색 0건, 응답 본문 테스트(정상·오류) |
| SC-10 | 승인 탭 실건 | ✅ Met | 에이전트 `block_ip` 요청 → 승인 탭 표시 → 화면 승인 → 실행, 감사 탭 "에이전트" |

**Success Rate**: 10/10 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 랩 + dry-run 기준, 실장비는 별도 사이클 | ✅ | 실장비 연결 조건 7가지를 `docs/firewall-admin-setup.md` §7에 남김 |
| [Plan] | Agent Builder 관리자 메뉴, 떼어낼 수 있는 모듈(기본 off) | ✅ | 코어가 모듈을 import하는 곳 0건(AST 계약 테스트), `main.py` 변경 3줄 |
| [Plan] | idt → fwctl 직접 호출 | ✅ | 수행자 식별 성공. 해제는 fwctl 계약상 actor가 없어 요청 ID에 사용자 ID를 실음 |
| [Plan] | 관측은 Grafana API 경유 | ✅ | Viewer 서비스 계정 토큰 1개로 알림·Loki 3경로 조회 |
| [Plan] | 이력은 fwctl 감사만, DB 변경 없음 | ✅ | 마이그레이션 0건 |
| [Plan] | admin 단독 + 확인창 | ✅ | LIVE 확인창에 경고 문구 |
| [Design] | Option C (조립 + 순수 검증·LogQL + 서비스 2 + 클라이언트 2) | ✅ | 검증·쿼리 조립을 I/O 없이 단위 테스트 |
| [Design] | 승인 API 무변경, 프론트 필터 | ✅ | `tool_id` 접미 판정이 실제 값(`mcp:<서버>:block_ip`)과 일치 |
| [Design] | 모드 전환 UI 없음 | ✅ | LIVE 전환은 fireware `.env`로만 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [firewall-admin-console.plan.md](../01-plan/features/firewall-admin-console.plan.md) | ✅ Finalized |
| Design | [firewall-admin-console.design.md](../02-design/features/firewall-admin-console.design.md) | ✅ v0.6 |
| Check | [firewall-admin-console.analysis.md](../03-analysis/firewall-admin-console.analysis.md) | ✅ Complete |
| 운영 | [firewall-admin-setup.md](../firewall-admin-setup.md) | ✅ 준비 절차·문제 해결 |
| Report | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01~03 | 기본 off·미설정 안내·admin 전용 | ✅ | |
| FR-04~11 | 상태·목록·차단·해제·검증·오류 매핑·요청 ID | ✅ | 형이 틀린 입력도 같은 코드 형식(Check G1) |
| FR-12~15 | 알림·로그·감사 조회, Grafana 장애 분리 | ✅ | 감사는 차단·해제만(폴링으로 쌓이는 list·health 제외) |
| FR-16~20 | 메뉴 조건부 노출·모드 배지·확인창·dry-run 문구·폴링 | ✅ | |
| FR-21 | "이 IP 차단" 초안 | ✅ | 룰 행 초안은 "{룰 이름} 탐지" — 알림 값이 건수가 아니어서 조정 |
| FR-22 | 승인 탭 | ✅ | 응답 지연 시 "처리됐을 수 있음" 안내 추가 |
| FR-23~24 | 이중 제출 방지·토큰 비노출 | ✅ | |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 보안 | 브라우저 → fwctl·Grafana 직접 호출 0건 | 0건(빌드 산출물·응답 검사) | ✅ |
| 보안 | LogQL에 사용자 입력을 그대로 넣지 않음 | 허용 목록·정규식 통과 값만 템플릿에 삽입, 주입 입력 테스트 | ✅ |
| 격리 | off일 때 기존 경로 불변, 코어 import 1곳 | AST 계약 테스트 6건 | ✅ |
| 성능 | 앱 수명 HTTP 클라이언트, fwctl 5초·Grafana 10초 | 적용 | ✅ |
| 가용성 | fwctl·Grafana 장애가 다른 화면에 영향 없음 | 브라우저 확인 | ✅ |
| 회귀 | 기존 테스트 실패 목록이 master와 같음 | 백엔드·프론트 신규 실패 0건 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 백엔드 모듈 | `idt/src/{domain,application,infrastructure}/firewall_admin/`, `src/api/firewall_admin_di.py`, `src/api/routes/admin_firewall_router.py`, `src/interfaces/schemas/firewall_admin.py` | ✅ |
| 설정 | `idt/src/config.py`(5개), `idt/.env.example` | ✅ |
| 프론트 | `idt_front/src/pages/AdminFirewallPage/`(페이지 + 탭 4개), `hooks/useFirewall.ts`, `hooks/useAdminNavGroups.ts`, `services/firewallService.ts`, `types/firewall.ts` | ✅ |
| 테스트 | 백엔드 248건 + 실측 5건, 프론트 98건 | ✅ |
| 문서 | Plan·Design v0.6·Analysis·Report, `docs/firewall-admin-setup.md` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority |
|------|--------|----------|
| `docs/SOURCE-OF-TRUTH.md` 반영 | Plan에서 "사용자 확인 후"로 둔 항목. 결정 대기 | Low |
| 실장비 연결(TLS·호출자별 토큰·대역 차단·영속화·감사 장기 보관·조직 승인) | 이번 범위 밖(Plan §1.4) | 별도 사이클 |
| 승인 API 응답 지연(에이전트 재개까지 동기 대기, 30초 초과 가능) | 기존 플랫폼 동작. 방화벽 승인 탭은 대응했으나 작업함은 같은 문제 | Medium |
| 승인 필요 MCP 도구에 `action` 카테고리를 주면 워커가 빠지는 문제 | 기존 플랫폼 동작. 운영 문서에 주의로 기록 | Medium |
| `RejectReasonDialog`를 `components/`로 이동 | 페이지 간 import 결합(G7) | Low |

### 4.2 Cancelled/On Hold

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final |
|--------|--------|-------|
| Design Match Rate | 90% | 97.8% (구조 97 · 기능 98 · 계약 95 · 실행 100) |
| Success Criteria | 10/10 | 10/10 |
| Critical/Important 갭 | 0 | 0 |
| Minor 갭 | — | 9건 → 코드 4건 수정, 5건 문서 반영 |
| `tsc -b` 신규 오류 | 0 | 0 (기존 211건 동일) |
| 변경 파일 린트 | 0 | 0 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 설계의 로그 필드명(`tcp_dport`)이 실제(`dest_port`)와 다름 | 실측 로그 기준으로 구현·설계 수정 | ✅ |
| fwctl 해제에 actor가 남지 않음 | 요청 ID `adm-<user_id>-…`로 수행자 추적 | ✅ |
| 이전 결과 안내가 다음 요청 뒤에 남음 | 새 요청 시 안내 지움 | ✅ (브라우저 확인에서 발견) |
| 과거 출발지에도 차단 버튼 | 발화·대기 인스턴스만 | ✅ (브라우저 확인에서 발견) |
| 알림 값 "1"을 측정값으로 표시 | 조건식 결과라 표시 제거 | ✅ (실측에서 발견) |
| 감사 탭이 캐시 결과 표시 | 매번 새로 조회 | ✅ |
| 승인 성공인데 화면은 "알 수 없는 오류" | 응답 없음(status 0)을 "처리됐을 수 있음"으로 안내, 목록 재조회 | ✅ (실건 승인에서 발견) |
| 형이 틀린 입력의 오류 형식 불일치(G1) | 라우터 전용 `route_class`로 같은 코드 형식 | ✅ |
| 메뉴 때문에 모든 관리자 화면이 30초마다 fwctl 조회(G5) | 메뉴는 갱신 없음, health 실패 debug | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **실측으로 설계를 고정했다.** Grafana 응답을 Viewer 토큰으로 직접 받아 픽스처로 저장하고, 로그 한 줄을 실제로 열어 본 덕에 필드명 오류(`tcp_dport`)를 구현 전에 잡았다.
- **기본 off + 조립 파일 1개.** 끄면 라우터·메뉴가 모두 사라지고, 코어 import 0건을 AST 테스트로 고정해 "특화는 코어에 하드코딩하지 않는다" 원칙을 지켰다.
- **화면 확인을 모듈마다 했다.** 단위 테스트가 모두 통과한 상태에서도 브라우저 확인이 결함 5건(안내 잔존, 과거 출발지 버튼, 무의미한 값, 캐시, 승인 오표시)을 찾았다.
- **정적 비교를 별도 에이전트에 맡겼다.** 제 판단에 기대지 않은 대조가 오류 형식 불일치(G1)와 전 화면 폴링(G5)을 찾았다.

### 6.2 What Needs Improvement (Problem)

- **설계가 외부 시스템의 실제 값을 가정했다.** 로그 필드명, 알림 `value`의 의미, `tool_id` 형식을 실측 전에 적었다가 고쳤다.
- **승인 연동에서 도구 카테고리를 잘못 지정해 시간을 썼다.** `block_ip`에 `action`을 지정했더니 워커가 빠졌고, 에이전트는 호출하지 않은 도구를 호출했다고 답했다.
- **worktree 밖 파일 편집 함정.** 기존 파일 Edit이 읽기 전이라 조용히 실패한 일이 있었다(계약 테스트가 잡음).

### 6.3 What to Try Next (Try)

- 외부 시스템과 붙는 기능은 Design 전에 실제 응답 1건씩을 받아 두고 설계한다.
- 승인 필요 MCP 도구를 등록할 때는 카테고리를 미분류로 두는 것을 기본 절차로 문서화한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Design | 외부 응답 형식을 가정으로 기술 | Design 체크리스트에 "외부 응답 실측 픽스처" 항목 |
| Do | 모듈 끝 브라우저 확인은 수동 스크립트 | 임시 서버·런처 스크립트를 `docs/firewall-admin-setup.md`에 정식 절차로 |
| Check | 정적 비교를 별도 에이전트에 위임 | 계속 유지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋·PR (worktree `feature/firewall-admin-console`, 변경 35파일 + 테스트·문서)
- [ ] `docs/SOURCE-OF-TRUTH.md` 반영 여부 결정
- [ ] 배포 시 `FIREWALL_ADMIN_*` 5개 설정과 Grafana 서비스 계정 준비(기본 off라 설정 없이 배포해도 기존 동작 불변)

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| fireware Phase 4: 방화벽 에이전트 프롬프트(`detection-policy.md`)·mcp-grafana 등록·스케줄 | High |
| 승인 API 응답 지연 해소(승인 즉시 응답 + 재개는 비동기) — 작업함 포함 | Medium |
| 실장비 연결(Plan §1.4) | 별도 |

---

## 9. Changelog

### v1.0.0 (2026-11-24)

**Added:**
- 관리자 API `/api/v1/admin/firewall/{status,blocks,blocks/{ip},alerts,events,audit}` (기본 off)
- 관리자 화면 "보안 운영 > 방화벽" — 상태 띠, 현황·탐지·감사·승인 탭
- 설정 `FIREWALL_ADMIN_ENABLED`·`FWCTL_URL`·`FWCTL_TOKEN`·`GRAFANA_URL`·`GRAFANA_TOKEN`
- 운영 문서 `docs/firewall-admin-setup.md`

**Changed:**
- 관리자 사이드바·상단 메뉴가 백엔드 기능 스위치에 따라 그룹을 숨김(`useAdminNavGroups`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-24 | Completion report created | 배상규 |
