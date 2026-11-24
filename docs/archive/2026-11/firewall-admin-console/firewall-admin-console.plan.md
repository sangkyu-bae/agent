# firewall-admin-console Planning Document

> **Summary**: fireware 방화벽 랩의 차단 현황 조회, 수동 차단·해제, 탐지 알림·차단 로그 조회, 감사 이력·에이전트 승인 확인을 Agent Builder 관리자 메뉴 한 화면에서 처리한다. idt 백엔드가 fwctl과 Grafana를 대신 호출하며, 설정이 꺼져 있으면 메뉴와 라우터가 노출되지 않는다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front) — 연동 대상: fireware, agent_mcp
> **Author**: 배상규
> **Date**: 2026-11-23
> **Status**: Draft
> **Type**: 풀스택 신규 기능 (떼어낼 수 있는 모듈, 기본 off)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 방화벽 차단 상태를 보거나 조작하려면 curl로 fwctl을 호출하고, 탐지 알림과 감사 이력은 Grafana에서, 에이전트의 `block_ip` 승인은 작업함에서 따로 확인해야 한다. 한 사건을 처리하는 데 도구 세 개를 오가야 하고, 수동 조작에는 "어느 사용자가 했는지"가 남지 않는다. |
| **Solution** | idt 백엔드에 `firewall_admin` 모듈을 추가해 fwctl(집행)과 Grafana API(알림·로그·감사)를 대신 호출하고, idt_front `/admin/firewall`에 탭 4개(현황·탐지·감사·승인) 화면을 만든다. 토큰은 서버에만 두고, 수동 조작의 `actor`에 로그인 사용자 ID를 넣는다. |
| **Function/UX Effect** | 관리자가 한 화면에서 dry-run/LIVE 모드와 현재 차단 목록을 보고, 사유를 적어 IP를 TTL 차단하거나 해제하고, 어떤 룰이 발화했는지와 최근 7일 감사 이력을 확인한다. 에이전트가 요청한 `block_ip` 승인 대기 건도 같은 화면에서 처리한다. |
| **Core Value** | 탐지 → 판단 → 승인 → 차단 → 감사 흐름을 사람이 한곳에서 감독할 수 있다. 화면은 fwctl 계약만 바라보므로 집행부를 실장비용으로 바꿔도 그대로 쓴다. |

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

## 1. Overview

### 1.1 Purpose

fireware 방화벽을 사람이 감독·조작하는 관리 화면을 Agent Builder 관리자 메뉴에 추가한다. 이번 사이클의 대상은 **Docker 랩 + dry-run 기본**이며, 실장비 연결은 조건 목록(§1.4)으로만 남긴다.

### 1.2 Background

세 저장소의 현재 상태(2026-11-23 확인):

| 구간 | 상태 |
|---|---|
| fireware 관측·집행 | Phase 0~3 완료(ulogd JSON → Alloy → Loki → Grafana, 탐지 룰 8개, fwctl). 브랜치 `worktree-log-stack-fwctl`에만 있고 `main`은 Phase 0 |
| fireware 컨테이너 | grafana·loki·alloy Up. firewall·fwctl·client·server는 종료 상태 |
| agent_mcp `mcp-firewall-server` | 구현 완료(도구 `block_ip`·`unblock_ip`·`list_blocks`·`firewall_health`). 컨테이너 미기동 |
| sangplusbot 연동(fireware Phase 4) | MCP 서버 등록, 방화벽 에이전트, 승인 게이트 지정, 스케줄 모두 미진행 |

사용자 결정(2026-11-23 질의):

| 항목 | 결정 |
|---|---|
| 목표 수준 | 랩 기준 관리 페이지. 실장비 연결은 별도 사이클 |
| 페이지 위치 | Agent Builder 관리자 메뉴(idt_front `/admin`), 떼어낼 수 있는 모듈 |
| 기능 | 현황 조회, 수동 차단·해제, 탐지 알림·차단 로그 조회, 감사 이력·에이전트 승인 연계 |
| 수동 차단 권한 | admin 단독 + 확인창. 사유 필수, 사용자 ID 감사 기록 |
| 집행 경로 | idt → fwctl 직접 호출 (`actor`에 사용자 ID) |
| 관측 데이터 | Grafana API 경유(서비스 계정 토큰 1개) |
| 에이전트 연동 | 코드 범위 밖. 준비 절차로 문서화 |
| 이력 보관 | fwctl 감사만 조회(Loki 7일). MySQL 테이블 추가 없음 |

### 1.3 Related Documents

- fwctl API 계약(SoT): `C:\Users\tkdrb\project\fireware\.claude\worktrees\log-stack-fwctl\docs\fwctl-api.md` v0.1.0
- 탐지 룰·행동 정책: 같은 worktree `docs/detection-policy.md`, `observability/grafana/provisioning/alerting/rules.yaml`
- MCP 게이트웨이: `C:\Users\tkdrb\project\agent\agent_mcp\mcp-firewall-server\CLAUDE.md`
- 위키: `docs/wiki/backend/patterns/detachable-module-seam.md`, `approval-gate-run-contract.md`, `app-lifetime-client-singleton.md`, `docs/wiki/frontend/patterns/layout-owned-nav-tabs.md`, `loading-button-pending-guard.md`, `docs/wiki/frontend/screens/admin-screens.md`
- 규칙: `docs/wiki/conventions/config-single-source-at-consumption.md`, `additive-contract-extension.md`

### 1.4 실장비 연결 조건 (이번 범위 밖, 기록용)

화면과 백엔드 모듈은 fwctl 계약만 바라보므로 아래가 채워지면 수정 없이 실장비에 붙는다.

| 조건 | 현재 | 필요한 것 |
|---|---|---|
| 집행부 | 컨테이너 netns의 ipset | 실 Linux 게이트웨이(nftables) 또는 상용 방화벽의 외부 차단 목록·API 어댑터 |
| 전송·인증 | 평문 HTTP, 공유 토큰 1개, 루프백 | TLS(mTLS), 호출자별 토큰 |
| 차단 단위 | IPv4 단일 주소, 출발지 기준 | IPv6·대역, NAT·공유 IP 오차단 대책 |
| 화이트리스트 | env 고정 7항목 | 업무망·협력사 대역 관리 절차 |
| 가용성 | 재기동 시 차단 목록 소실, 단일 인스턴스 | 영속화·이중화 |
| 감사 | 파일 무기한, Loki 7일 | 장기 보관·위변조 방지 |
| 조직 | 없음 | 변경관리·정보보호 부서 승인, 로그의 외부 LLM 전송 검토 |

---

## 2. Scope

### 2.1 In Scope

**M1. 백엔드 — fwctl 프록시 (`idt/`)**
- [ ] `firewall_admin` 모듈: domain(IPv4·TTL·사유 검증), application(유스케이스), infrastructure(`FwctlClient` httpx)
- [ ] 라우터 `admin_firewall_router.py`, 전 엔드포인트 `require_role("admin")`
- [ ] `GET /api/v1/admin/firewall/status` — fwctl `/healthz` + 모듈 설정 상태
- [ ] `GET /api/v1/admin/firewall/blocks` — 차단 목록
- [ ] `POST /api/v1/admin/firewall/blocks` — 수동 차단(`actor=sangplusbot/admin:<user_id>`)
- [ ] `DELETE /api/v1/admin/firewall/blocks/{ip}` — 해제
- [ ] 설정 5종(§8.3)과 조립. `firewall_admin_enabled=false`(기본)면 라우터를 등록하지 않는다

**M2. 백엔드 — Grafana 조회**
- [ ] `GrafanaClient`(서비스 계정 토큰): 알림 상태 조회, Loki 데이터소스 쿼리
- [ ] `GET /api/v1/admin/firewall/alerts` — 탐지 룰 8개의 발화 상태(`rule_id`·`severity`·`src_ip`·`action_hint`)
- [ ] `GET /api/v1/admin/firewall/events` — 차단 로그(출발지 IP별 집계 + 최근 N건, 기간·action 필터)
- [ ] `GET /api/v1/admin/firewall/audit` — fwctl 감사 이력(`{job="fwctl"}`, 최근 7일, event·actor·ip 필터)
- [ ] LogQL은 서버가 고정 템플릿으로 조립한다. 클라이언트가 쿼리 문자열을 보내지 않는다

**M3. 프론트 — 현황·수동 조작 (`idt_front/`)**
- [ ] `/admin/firewall` 페이지, `adminNav.ts`에 "보안 운영" 그룹과 "방화벽" 항목 추가(설정 off면 숨김)
- [ ] 상단 상태 띠: fwctl 생존, **DRY-RUN/LIVE 배지**, TTL 상한, ipset 상태
- [ ] 현황 탭: 차단 목록(IP·남은 TTL·패킷 수), 행별 해제 버튼, 10초 폴링
- [ ] 차단 폼: IP·TTL·사유 입력 → 확인창(모드·IP·TTL·사유 재표시) → 결과에 `dry_run` 표시

**M4. 프론트 — 탐지·감사·승인 탭**
- [ ] 탐지 탭: 발화 중인 룰 목록, 출발지 IP Top N, 최근 차단 로그. 행에서 "이 IP 차단"으로 폼 채우기
- [ ] 감사 탭: 시각·이벤트·actor·IP·TTL·사유·결과·dry_run 표, 필터
- [ ] 승인 탭: `block_ip`·`unblock_ip` 승인 대기 건 목록, 기존 승인 API로 승인·거절
- [ ] Grafana 대시보드 바로가기 링크

**M5. 연동 준비 절차·검증**
- [ ] fireware worktree 브랜치를 `main`에 반영하고 랩 전체 재기동(firewall·fwctl 동시)
- [ ] Grafana 서비스 계정(Viewer) 토큰 발급 절차 문서화
- [ ] sangplusbot 연동 절차 문서화: mcp-firewall-server(8008)·mcp-grafana 등록 → MCP 동기화 → `block_ip` 승인 필요 지정 → 방화벽 에이전트 구성(프롬프트 원본 `detection-policy.md`) → 스케줄
- [ ] `idt/.env.example`·`docs/SOURCE-OF-TRUTH.md` 반영 여부는 사용자 확인 후

### 2.2 Out of Scope

- 실장비 연결(§1.4 전 항목)
- dry-run ↔ LIVE 전환 UI. 모드는 fireware `.env`로만 바꾼다
- 화이트리스트·TTL 상한·탐지 룰 임계치 편집 UI. 화면은 값을 표시만 한다
- 영구 차단, 대역(CIDR) 차단, IPv6
- 2인 승인(요청자와 다른 관리자 승인)
- MySQL 이력 테이블과 마이그레이션
- 방화벽 에이전트·스케줄의 코드 자동 생성(시드 스크립트). 화면 조작 절차만 문서화
- fwctl·mcp-firewall-server 코드 변경. 계약 v0.1.0 그대로 사용
- 실시간 푸시(WebSocket). 폴링으로 처리
- admin 외 역할(부서 관리자 등)에 대한 세분 권한

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `firewall_admin_enabled=false`면 `/api/v1/admin/firewall/*` 라우터가 등록되지 않는다(404). 기본값 false | High | Pending |
| FR-02 | 활성화됐는데 fwctl URL·토큰이 비어 있으면 기동 로그에 warning을 남기고, status 응답이 `configured=false`를 돌려준다(조용히 꺼지지 않는다) | High | Pending |
| FR-03 | 모든 엔드포인트는 admin 역할만 호출할 수 있다. 무토큰 401, 일반 사용자 403 | High | Pending |
| FR-04 | `GET /status` → `{enabled, configured, reachable, dry_run, max_ttl_seconds, ipset_exists, version, grafana_configured}`. fwctl 불통이면 200 + `reachable=false` | High | Pending |
| FR-05 | `GET /blocks` → `{items[{ip, ttl_remaining_seconds, packets, bytes}], count, dry_run}` | High | Pending |
| FR-06 | `POST /blocks {ip, ttl_seconds?, reason}` → fwctl `POST /v1/blocks`. `actor`는 서버가 `sangplusbot/admin:<user_id>`로 채우며 클라이언트 입력을 받지 않는다 | High | Pending |
| FR-07 | 차단 요청은 서버에서 IPv4 단일 주소·TTL `[1, max]`·사유 1~500자를 먼저 검증한다(422). 화이트리스트 판정은 fwctl에 맡기고 403 `FORBIDDEN_WHITELIST`를 그대로 전달한다 | High | Pending |
| FR-08 | 차단 응답에 `dry_run`과 `expires_at`, `request_id`를 포함한다 | High | Pending |
| FR-09 | `DELETE /blocks/{ip}` → 해제. fwctl 404는 `already_absent=true`인 200으로 돌려준다 | High | Pending |
| FR-10 | fwctl 오류는 코드와 함께 전달한다: 401→502 `FWCTL_AUTH_FAILED`, 타임아웃→504 `FWCTL_TIMEOUT`, 연결 실패→502 `FWCTL_UNAVAILABLE`, 500 `AUDIT_ERROR`→502 `FWCTL_AUDIT_ERROR`("차단은 적용됐으나 감사 미기록" 문구 포함). 재시도 없음 | High | Pending |
| FR-11 | 요청마다 `X-Request-Id`를 fwctl에 전달해 idt 로그와 fwctl 감사를 같은 값으로 찾을 수 있다 | Medium | Pending |
| FR-12 | `GET /alerts` → Grafana 알림 그룹 `firewall-detection`의 발화·대기 인스턴스 목록(`rule_id`, `kind`, `severity`, `action_hint`, `src_ip`, `state`, `active_at`) | High | Pending |
| FR-13 | `GET /events?range=&action=` → 출발지 IP별 건수 Top N과 최근 로그 N건(시각·src·dst·포트·프로토콜·action). `range`는 허용 목록(15m·1h·6h·24h) | High | Pending |
| FR-14 | `GET /audit?range=&event=&ip=&actor=` → fwctl 감사 레코드 목록. `range` 최대 7d. 필터 값은 서버가 형식 검증 후 LogQL 템플릿에 넣는다 | High | Pending |
| FR-15 | Grafana 미설정·불통이면 alerts·events·audit는 503 `GRAFANA_UNAVAILABLE`을 돌려주고, 현황 탭(fwctl)은 영향받지 않는다 | High | Pending |
| FR-16 | 관리자 메뉴 "보안 운영 > 방화벽"은 status가 `enabled=true`일 때만 보인다. 꺼져 있을 때 `/admin/firewall` 직접 진입은 안내 문구를 보여 준다 | High | Pending |
| FR-17 | 상태 띠에 DRY-RUN(노랑)/LIVE(빨강) 배지를 항상 표시한다. fwctl 불통이면 "연결 안 됨"을 표시하고 차단 폼을 비활성화한다 | High | Pending |
| FR-18 | 차단 폼 제출 전 확인창이 모드·IP·TTL·사유를 다시 보여 준다. LIVE 모드면 경고 문구를 추가한다 | High | Pending |
| FR-19 | 차단 결과가 `dry_run=true`면 "실제로 차단되지 않았습니다"를 표시한다 | High | Pending |
| FR-20 | 차단 목록은 10초 간격으로 갱신하고, 남은 TTL을 초 단위로 줄여 표시한다. 차단·해제 성공 시 즉시 다시 조회한다 | Medium | Pending |
| FR-21 | 탐지 탭의 알림·로그 행에서 "이 IP 차단"을 누르면 차단 폼에 IP와 사유 초안(룰 ID·건수)이 채워진다. *(Design v0.4: 알림 인스턴스 값은 건수가 아니어서 룰 행 초안은 "{룰 이름} 탐지", 건수는 출발지 상위 행에서만 넣는다)* | Medium | Pending |
| FR-22 | 승인 탭은 도구 이름이 `block_ip`·`unblock_ip`인 승인 대기 건만 보여 주고 기존 `/api/v1/approvals/{id}/approve|reject`로 처리한다. 대상 건이 없으면 빈 상태와 연동 준비 안내를 보여 준다 | Medium | Pending |
| FR-23 | 차단·해제 버튼은 `LoadingButton`을 쓰고 처리 중 이중 제출을 막는다 | High | Pending |
| FR-24 | fwctl·Grafana 토큰은 어떤 API 응답·프론트 번들·로그에도 포함되지 않는다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 보안 | 브라우저 → fwctl·Grafana 직접 호출 0건. 토큰은 `idt/.env`에만 존재 | 네트워크 탭 확인, 번들 문자열 검색, 응답 스키마 테스트 |
| 보안 | LogQL·URL에 사용자 입력을 그대로 넣지 않는다(허용 목록·정규식 검증 후 템플릿) | 단위 테스트(따옴표·중괄호·파이프 주입 입력) |
| 격리 | 모듈 off일 때 기존 경로 동작 불변. `firewall_admin` 밖에서 이 모듈을 import하는 곳은 조립부 한 곳 | AST import 계약 테스트 |
| 성능 | HTTP 클라이언트는 앱 수명 싱글턴. fwctl 타임아웃 5초, Grafana 10초 | 코드 리뷰, 응답 시간 측정 |
| 가용성 | fwctl·Grafana 장애가 다른 관리자 화면·채팅 경로에 영향을 주지 않는다 | 불통 상태 수동 확인 |
| 회귀 | 백엔드·프론트 기존 테스트의 실패 목록이 master와 같다 | 정렬된 `FAILED` 목록 diff |
| 접근성 | 모드 배지는 색과 글자를 함께 쓴다. 확인창은 키보드로 조작할 수 있다 | 수동 확인 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] **SC-1 (off 격리)**: 설정 off에서 `/api/v1/admin/firewall/status`가 404이고 관리자 메뉴에 "방화벽"이 없다
- [ ] **SC-2 (권한)**: 일반 사용자 토큰으로 전 엔드포인트 403, 무토큰 401
- [ ] **SC-3 (dry-run 왕복)**: 랩 dry-run에서 화면으로 `172.28.10.66` TTL 60 차단 → 결과에 "실제로 차단되지 않았습니다" → 해제까지 오류 없이 끝난다
- [ ] **SC-4 (사용자 식별)**: SC-3 직후 fwctl 감사에 `actor=sangplusbot/admin:<user_id>`와 같은 `request_id`가 남고, 감사 탭에서 그 행이 보인다
- [ ] **SC-5 (안전장치 전달)**: 화면에서 `172.28.10.10`(화이트리스트) 차단 시도 → `FORBIDDEN_WHITELIST` 문구 표시. TTL 99999 → 서버 422
- [ ] **SC-6 (LIVE 왕복)**: fireware를 `FWCTL_DRY_RUN=false`로 올린 뒤 attacker 차단 → 목록에 남은 TTL 표시 → 탐지 탭에서 `action=block` 로그 확인 → TTL 만료 후 목록에서 사라짐
- [ ] **SC-7 (탐지)**: attacker 가동 후 탐지 탭에 발화 룰과 `src_ip=172.28.10.66`이 보이고 "이 IP 차단"이 폼을 채운다
- [ ] **SC-8 (장애 분리)**: Grafana를 내린 상태에서 현황 탭 정상, 탐지·감사 탭은 안내 문구. fwctl을 내린 상태에서 "연결 안 됨" + 폼 비활성
- [ ] **SC-9 (토큰 비노출)**: 프론트 빌드 산출물과 전 API 응답에서 토큰 문자열 검색 0건
- [ ] **SC-10 (연동 준비 문서)**: 준비 절차대로 MCP 서버 등록과 승인 지정을 마쳤을 때 승인 탭에 `block_ip` 대기 건이 보인다(연동 미완료 시 이월로 기록)

### 4.2 Quality Criteria

- [ ] 백엔드: domain 검증·유스케이스·`FwctlClient` 상태코드 매핑(`httpx.MockTransport`)·`GrafanaClient` 응답 파싱·라우터 권한 테스트를 구현보다 먼저 작성
- [ ] 프론트: 훅·폼·확인창·모드 배지·탭별 빈 상태·오류 상태를 Vitest + RTL + MSW로 검증
- [ ] 실제 fwctl dry-run 왕복 1회와 실제 Grafana 조회 1회를 Do 단계 안에서 실행(가짜 응답만으로 완료 처리하지 않는다)
- [ ] `tsc -b`, 린트 오류 0(변경 파일 기준, master 대비 신규 0)
- [ ] 회귀는 `FAILED` 목록 diff로 증명

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 웹 화면이 차단 권한의 새 진입점이 된다(계정 탈취·권한 우회) | High | Low | admin 전용, 서버 검증, fwctl 안전장치(화이트리스트·TTL 상한·dry-run 기본) 유지, 모든 조작이 사용자 ID와 함께 감사에 남음. 모듈 기본 off |
| LIVE 모드에서 오조작으로 정상 IP 차단 | High | Low | 확인창에 모드 경고, TTL 필수(최대 3600초), 영구 차단 없음, 목록에서 즉시 해제 |
| dry-run 결과를 실제 차단으로 오해 | Medium | Medium | 상태 띠 배지 상시 표시, 결과 문구 "실제로 차단되지 않았습니다", 목록에는 실제 ipset 내용만 표시 |
| fwctl 토큰이 idt 프로세스에 추가로 존재(노출 면 증가) | Medium | Low | `.env`로만 주입, 로그 마스킹 대상 키 확인, 응답 스키마에 토큰 필드 없음(테스트 고정). 호출자별 토큰은 §1.4로 이월 |
| LogQL 주입(필터 값에 쿼리 조각 삽입) | Medium | Medium | 서버 고정 템플릿, IP는 `ipaddress` 정규화, event·range는 허용 목록, actor는 `[A-Za-z0-9._:/-]{1,100}`만 허용 |
| Grafana 알림 API·데이터소스 쿼리 응답 형식이 버전에 따라 다름 | Medium | Medium | Design 단계에서 실행 중인 Grafana(12.x)에 실제 호출해 응답을 고정. 파싱 실패는 503으로 드러냄 |
| 승인 목록 API가 도구 이름 필터를 지원하지 않음(현재 status 필터만) | Medium | High | Design에서 선택: 선택적 쿼리 파라미터 추가(기존 호출 무변경) 또는 프론트 필터. 기존 소비자 회귀 테스트 |
| 방화벽 전용 화면이 코어에 들어가 "특화는 데이터로" 원칙과 충돌 | Medium | High | 떼어낼 수 있는 모듈: 설정 off면 라우터·메뉴 없음, 코어 → 모듈 import는 조립부 한 곳, DB 변경 없음. AST 계약 테스트로 고정 |
| fireware 랩이 내려가 있어 검증 불가 | Medium | High(현재) | M5 선행 작업으로 worktree 반영·전체 재기동. firewall만 재시작하면 fwctl이 고아가 되므로 둘을 함께 올린다 |
| 에이전트 연동이 안 끝나 승인 탭을 실제 건으로 확인하지 못함 | Low | Medium | 승인 탭은 MSW 테스트로 검증하고 SC-10은 연동 완료 시 확인, 미완료면 이월 항목으로 기록 |
| 감사 이력이 Loki 7일로 제한 | Low | High | 화면에 "최근 7일" 명시. fwctl 감사 파일은 무기한 보존. 장기 보관은 §1.4 |
| idt 컨테이너 배포 시 `127.0.0.1`이 자기 자신을 가리킴 | Low | Medium | URL은 설정값. 컨테이너 배포는 `host.docker.internal` 사용을 문서에 명시 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `idt/src/config.py` | Config | `firewall_admin_*` 설정 5종 추가(기본 off) |
| `idt/src/api/main.py` | DI/Router | 조립 함수 1개와 조건부 `include_router` 1건 추가 |
| `idt/src/api/routes/admin_firewall_router.py` | API | 신규 라우터(엔드포인트 7개) |
| `idt/src/{domain,application,infrastructure}/firewall_admin/` | Module | 신규 모듈 |
| `idt/src/api/routes/approval_router.py` | API | (Design에서 결정) 승인 목록에 선택적 도구 이름 필터 추가 가능 |
| `idt_front/src/constants/adminNav.ts` | Config | 그룹 key에 `'security'` 추가, "보안 운영 > 방화벽" 항목 |
| `idt_front/src/constants/api.ts` | Config | `ADMIN_FIREWALL_*` 상수 |
| `idt_front/src/pages/AdminFirewallPage/`, `src/types/firewall.ts`, `src/services/`, `src/hooks/` | UI | 신규 페이지·타입·서비스·훅 |
| 라우트 정의(App 라우터) | UI | `/admin/firewall` 경로 추가 |
| DB | Schema | **변경 없음** |
| fireware / agent_mcp | 외부 저장소 | 코드 변경 없음. fireware는 브랜치 반영·재기동, Grafana 서비스 계정 발급만 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `adminNav.ts` `ADMIN_NAV_GROUPS` | READ | AdminLayout 사이드바, AdminSectionTabs, TopNav ADMIN_MENU | Needs verification: 그룹 추가·조건부 숨김. 개수 하드코딩 단언이 있는 테스트 확인 |
| `AdminNavGroup['key']` 유니온 | TYPE | 위 3개 소비처 | Needs verification: `'security'` 추가 시 switch·Record 누락 여부 |
| `ADMIN_ENTRY_PATH` | READ | 관리자 진입 경로 | None: 첫 그룹 첫 항목 유지(새 그룹은 뒤에 추가) |
| `GET /api/v1/approvals` | READ | 작업함·알림 벨·채팅 승인 카드 | Needs verification: 필터 파라미터를 추가하면 선택 인자라 기존 호출 무변경이어야 함 |
| `POST /api/v1/approvals/{id}/approve|reject` | UPDATE | 작업함 | None: 그대로 재사용 |
| `main.py` 라우터 등록 | RUN | 전체 앱 기동 | Needs verification: off일 때 기동 경로 불변, on인데 미설정이어도 기동 성공 |
| fwctl `/v1/blocks` | CREATE/DELETE | mcp-firewall-server(`actor=mcp-firewall-server/...`) | None: 호출자가 하나 늘 뿐이며 actor 접두로 구분 |
| Grafana `:3000` | READ | 사람(브라우저), 예정된 mcp-grafana | None: 조회 전용 서비스 계정 추가 |

### 6.3 Verification

- [ ] 관리자 메뉴 3개 소비처가 그룹 추가 후에도 동작(사이드바·탭·드롭다운)
- [ ] 설정 off에서 백엔드 기동 로그와 라우트 목록이 변경 전과 같다
- [ ] 승인 목록 기존 호출(작업함·알림 벨)의 응답이 변경 전과 같다
- [ ] mcp-firewall-server의 integration 테스트가 그대로 통과(fwctl 계약 불변)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 단위 모듈, 백엔드 연동 | 풀스택 웹 앱 | ☐ |
| **Enterprise** | 레이어 분리, DI | 기존 idt 구조(domain/application/infrastructure) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 화면 위치 | Agent Builder 관리자 / fireware 독립 UI / Grafana만 | **Agent Builder 관리자** | 로그인·권한·승인함 재사용 (사용자 결정) |
| 모듈 형태 | 코어 상시 기능 / 떼어낼 수 있는 모듈 | **떼어낼 수 있는 모듈, 기본 off** | "특화는 코어에 하드코딩 금지" 원칙. off면 라우터·메뉴 없음 |
| 집행 경로 | fwctl 직접 / MCP 서버 경유 | **fwctl 직접** | `actor`에 사용자 ID를 넣어 감사에 남김 (사용자 결정) |
| 화이트리스트 검증 | idt에도 복제 / fwctl에 위임 | **fwctl에 위임** | 목록 복제는 세 번째 사본이 되어 어긋날 수 있음. 사람 조작은 403을 그대로 보여 주면 충분 |
| 관측 데이터 | Grafana API / Loki 직접 / 링크만 | **Grafana API** | 토큰 1개, fireware compose 변경 없음 (사용자 결정) |
| 이력 저장 | fwctl 감사 조회 / MySQL 추가 | **fwctl 감사 조회** | 출처 한 곳, 마이그레이션 없음 (사용자 결정) |
| 모드 전환 | UI 토글 / env만 | **env만** | 웹에서 LIVE 전환을 막아 오조작 범위 축소 |
| 갱신 방식 | 폴링 / WebSocket | **TanStack Query 폴링 10초** | 관리자 소수 사용, 구현 단순 |
| 승인 연계 | 기존 승인 API 재사용 / 전용 API | **기존 API 재사용** | 승인 상태 전이 계약을 건드리지 않음 |
| HTTP 클라이언트 | 요청마다 생성 / 앱 수명 싱글턴 | **앱 수명 싱글턴** | 위키 `app-lifetime-client-singleton` |
| 메뉴 노출 판정 | 프론트 env / 백엔드 status | **백엔드 status** | 설정 출처를 백엔드 한 곳으로 유지 |
| 프론트 상태 | TanStack Query(서버 상태) + 로컬 state(폼) | 좌동 | 기존 규칙 |
| 테스트 | pytest / Vitest + RTL + MSW | 좌동 | 기존 규칙, TDD |

Design에서 정할 항목: Grafana 알림·쿼리 API의 정확한 경로와 응답 형식(실측), 승인 목록 도구 필터 방식, off 상태에서 status 엔드포인트만 남길지 여부(메뉴 판정용), 탭 구성 세부.

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 idt 레이어)

[브라우저 /admin/firewall]
   │  JWT (admin)
   ▼
[idt] admin_firewall_router ── require_role("admin")
   │
   ├─ application/firewall_admin   유스케이스: status / list / block / unblock / alerts / events / audit
   │     ├─ domain/firewall_admin  IPv4·TTL·사유 검증, LogQL 템플릿(순수)
   │     └─ ports (Protocol)       FwctlPort, GrafanaPort
   └─ infrastructure/firewall_admin
         ├─ FwctlClient   ──HTTP + Bearer + X-Request-Id──► fwctl :8070 ──► ipset
         └─ GrafanaClient ──HTTP + 서비스 계정 토큰──────► Grafana :3000 ──► Loki / 알림

idt_front/
├─ src/pages/AdminFirewallPage/     상태 띠 + 탭 4개(현황·탐지·감사·승인)
├─ src/types/firewall.ts            응답 타입·상수(as const)
├─ src/services/firewallService.ts
├─ src/hooks/useFirewall*.ts        TanStack Query
└─ src/constants/{adminNav,api}.ts
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 3종(루트·idt·idt_front) 규칙 존재
- [x] 위키 패턴 문서(§1.3) 존재
- [x] ESLint·TypeScript 설정 존재
- [x] TDD 원칙(테스트 먼저)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **모듈 이름** | 없음 | 백엔드 `firewall_admin`, 라우터 접두 `/api/v1/admin/firewall`, 프론트 `AdminFirewallPage` | High |
| **actor 형식** | fwctl 계약: 1~100자 자유 문자열 | `sangplusbot/admin:<user_id>` 고정. 에이전트 경로는 `mcp-firewall-server/...` | High |
| **오류 코드** | fwctl·MCP 서버에 정의됨 | MCP 서버와 같은 이름 사용(`FWCTL_AUTH_FAILED`·`FWCTL_TIMEOUT`·`FWCTL_UNAVAILABLE`·`FWCTL_AUDIT_ERROR`) + `GRAFANA_UNAVAILABLE` | High |
| **설정 키** | `prompt_guard_*` 형식 선례 | `firewall_admin_*`, 각 키에 소비 지점 주석 | High |
| **프론트 상수** | 컴포넌트 파일 런타임 export 금지 | 탭 키·range 목록은 `src/types/firewall.ts`에 `as const` | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | Default | To Be Created |
|----------|---------|-------|---------|:-------------:|
| `FIREWALL_ADMIN_ENABLED` | 모듈 사용 여부 | idt | `false` | ☐ |
| `FIREWALL_ADMIN_FWCTL_URL` | fwctl base URL | idt | `http://127.0.0.1:8070` | ☐ |
| `FIREWALL_ADMIN_FWCTL_TOKEN` | fwctl Bearer(fireware `FWCTL_TOKEN`과 같은 값) | idt | 없음 | ☐ |
| `FIREWALL_ADMIN_GRAFANA_URL` | Grafana base URL | idt | `http://127.0.0.1:3000` | ☐ |
| `FIREWALL_ADMIN_GRAFANA_TOKEN` | Grafana 서비스 계정 토큰(Viewer) | idt | 없음 | ☐ |

프론트 환경변수 추가는 없다.

### 8.4 Pipeline Integration

9단계 파이프라인은 쓰지 않는다. PDCA 단일 feature로 진행한다.

---

## 9. Next Steps

1. [ ] Plan 검토·확정
2. [ ] `/pdca design firewall-admin-console` — 포함할 것: 엔드포인트 7개 요청·응답 스키마, fwctl 오류 매핑 표, Grafana API 실측 결과와 LogQL 템플릿, 탭별 화면 구성과 UI 체크리스트, 모듈 on/off 조립 방식, 승인 필터 방식, 테스트 계획, 모듈별 세션 가이드
3. [ ] 선행 작업(M5 일부): fireware worktree 브랜치 반영·랩 전체 재기동, Grafana 서비스 계정 토큰 발급
4. [ ] worktree 생성 후 `/pdca do firewall-admin-console --scope module-1` 부터 순서대로 진행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-23 | Initial draft. 결정 확정: 랩 기준, 관리자 메뉴(떼어낼 수 있는 모듈), 기능 4종, admin 단독 + 확인창, fwctl 직접 호출, Grafana API 경유, 연동은 준비 절차, 이력은 fwctl 감사 조회 | 배상규 |
