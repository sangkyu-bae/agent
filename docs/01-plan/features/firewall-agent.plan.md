# firewall-agent Planning Document

> **Summary**: fireware Phase 4. 탐지 정책(`detection-policy.md`)대로 판단하는 보안 에이전트를 sangplusbot에 만들고, 10분 스케줄과 Grafana 알림 웹훅으로 자동 실행한다. 에이전트는 고정 조회 도구로 발화 알림과 IP 맥락을 보고 `block_ip`를 요청하며, 실행은 사람이 방화벽 화면에서 승인한 뒤에만 일어난다. 관리자는 방화벽 화면에서 자동 실행을 끄고 켠다.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front) — 연동: agent_mcp(조회 도구), fireware(정책·웹훅 설정)
> **Author**: 배상규
> **Date**: 2026-11-24
> **Status**: Draft
> **Type**: 저장소 3개에 걸친 연동 기능. sangplusbot 쪽은 일반 기능 2개(알림 수신, 자동 실행 건너뜀) + 방화벽 모듈 확장

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 방화벽 랩은 탐지(Grafana 알림 8개)와 집행(fwctl·mcp-firewall-server)까지 갖췄지만, "이 IP를 막을지, 얼마나 막을지"를 판단하는 주체가 없다. 지금은 사람이 Grafana를 보고 방화벽 화면에서 직접 차단한다. 탐지 정책 문서는 있으나 실행하는 에이전트가 없다. |
| **Solution** | ① agent_mcp에 읽기 전용 조회 도구 2개(`list_detections`, `get_ip_context`)를 만들어 LLM이 LogQL을 쓰지 않게 한다. ② sangplusbot에 Alertmanager 형식 알림 수신 기능과 "실행 중·승인 대기 중이면 자동 실행 건너뜀" 옵션을 일반 기능으로 추가한다. ③ 정책에서 파생한 프롬프트로 보안 에이전트를 만들고 10분 스케줄과 알림 웹훅에 연결한다. ④ 방화벽 화면에 자동 점검 토글을 둔다. |
| **Function/UX Effect** | 공격이 시작되면 알림 웹훅이 즉시, 놓친 건은 10분 스케줄이 에이전트를 깨운다. 에이전트는 IP별로 분류·TTL·사유를 정해 차단을 요청하고, 관리자는 방화벽 화면 승인 탭에서 근거를 보고 승인한다. 정상 트래픽·보호 대상 주소·검증 안 된 룰은 차단하지 않고 보고만 한다. |
| **Core Value** | 탐지 → 판단 → 승인 → 차단 → 감사가 사람 감독 아래 자동으로 돈다. 알림 수신과 건너뜀 옵션은 방화벽 전용이 아니라 다른 모니터링 알림·스케줄 에이전트에도 쓰인다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 탐지와 집행 사이의 판단 단계가 사람 수작업이다. 정책 문서는 있으나 실행 주체가 없다 |
| **WHO** | 1차: Agent Builder 관리자(방화벽 화면에서 승인·토글). 2차: 같은 일반 기능(알림 수신·건너뜀)을 쓰는 다른 에이전트 소유자 |
| **RISK** | LLM 판단 오류로 잘못 막거나 같은 IP 요청이 쌓이는 것. 승인 게이트·fwctl 안전장치·dry-run 3중 방어와 건너뜀 옵션으로 막는다 |
| **SUCCESS** | dry-run 랩에서 시나리오(스캔·정상·보호 주소·승인 대기·웹훅·토글)를 통과하고, LIVE 1회로 승인 → 실차단 → 원복까지 확인한다 |
| **SCOPE** | M1 조회 도구(agent_mcp) → M2 건너뜀 옵션·트리거 스크립트 → M3 알림 수신 → M4 방화벽 화면 토글 → M5 에이전트 구성·정책 v0.2·웹훅 활성화 → M6 시나리오·모델 비교·LIVE 1회 |

---

## 1. 개요

### 1.1 목적

fireware 로드맵 Phase 4("연동")를 마친다. Phase 4 원안은 "mcp-grafana 등록 + 에이전트 작성 + 스케줄 트리거"였으나, 조사 결과(§1.2)에 따라 조회는 고정 도구로, 트리거는 스케줄과 알림 웹훅 두 경로로 바꾼다. 이번 사이클의 대상은 **Docker 랩 + dry-run 기본**이고, 시나리오를 통과하면 LIVE로 1회 실차단을 확인한 뒤 dry-run으로 되돌린다.

### 1.2 배경

**Phase 4 현황 (2026-11-24 확인)**

| 항목 | 상태 |
|---|---|
| mcp-firewall-server (agent_mcp) | 구현됨. 도구 `block_ip`·`unblock_ip`·`list_blocks`·`firewall_health`. 컨테이너 `agent_mcp-mcp-firewall-server-1`(8008) 가동. agent_mcp 저장소는 미커밋 변경이 많다 |
| sangplusbot MCP 등록·승인 | firewall-admin-console 검증 때 로컬 등록. `block_ip`·`unblock_ip` 승인 필요, 카테고리 미분류. 승인은 방화벽 화면 승인 탭에서 처리 |
| 보안 에이전트 | 없음. 검증용 `[E2E] 방화벽 차단 검증` 에이전트만 있다 |
| 조회 도구 | 없음(mcp-grafana 미등록) |
| 자동 실행 | 스케줄 기능은 있으나 트리거(`POST /api/v1/internal/schedules/trigger`)를 매 분 호출할 주체가 로컬에 없다 |
| fireware 웹훅 템플릿 | `observability/grafana/webhook-templates/`에 비활성으로 있음(Bearer 토큰, `group_by: [src_ip, rule_id]`, `maxAlerts: 20`) |

**조사에서 확인한 사실**

| # | 사실 | 계획에 준 영향 |
|---|---|---|
| F1 | mcp-grafana v2.3.0 README에는 발화 중인 알림 인스턴스를 `src_ip` 라벨과 함께 주는 도구가 없다(알림 도구는 룰 조회·라우팅·사일런스). Loki 조회는 LLM이 LogQL을 직접 쓴다 | 고정 조회 도구로 대체 |
| F2 | 스케줄 cron 최소 간격 10분(`SchedulePolicy.MIN_CRON_INTERVAL_MINUTES`). 정책 문서는 5분 가정 | 10분으로 정책 수정, 웹훅으로 보완 |
| F3 | 승인 대기 중복 방지가 없다. 승인 저장소에 에이전트별 대기 건 조회 메서드도 없다 | 건너뜀 옵션 신설 |
| F4 | sangplusbot 공개 웹훅은 HMAC 서명(`sha256=`, `"{ts}." + 본문`) + `{query ≤ 2000자}` 본문만 받고, 에이전트 실행이 끝날 때까지 응답을 붙잡는다. fireware 템플릿은 Bearer + Grafana JSON | 알림 수신 기능 신설 |
| F5 | 시스템 프롬프트 최대 8,000자, 스케줄 지침 최대 1,900자. 정책 문서는 180줄 | 정책을 압축한 프롬프트 파일 필요 |
| F6 | 스케줄 켜기/끄기는 에이전트 소유자만 가능(`agent_schedule/access.py`) | 방화벽 화면 토글의 소유권 처리를 Design에서 결정 |
| F7 | 스케줄 실행 경로는 `auth_ctx` 없이 `RunAgentUseCase.execute`를 호출하고, 승인 게이트는 이 경로에서도 승인 요청을 영속한다 | 스케줄 실행에서 MCP 도구 권한·승인 동작을 실측으로 확인 |
| F8 | 승인 필요 MCP 도구에 카테고리 `action`을 주면 워커에서 빠져 에이전트가 호출하지 못한다(지난 사이클 확인) | 새 도구도 미분류로 등록 |

**사용자 결정 (2026-11-24 질의)**

| 항목 | 결정 |
|---|---|
| 조회 도구 | 고정 조회 도구 `list_detections`·`get_ip_context` (mcp-grafana 대신) |
| 트리거 | 스케줄(10분) + Grafana 알림 웹훅 둘 다. 관리자가 끄고 켤 수 있게 |
| 트리거 호출 주체 | `idt/scripts/`의 매 분 호출 스크립트 (운영은 기존 문서대로 OS cron·k8s CronJob) |
| 중복 요청 | 승인 대기 중이면 회차 건너뜀 |
| 웹훅 수신 | sangplusbot에 Alertmanager 형식 알림 수신 기능 추가 |
| 켜고 끄기 | 방화벽 관리 화면에 자동 점검 토글 |
| 모델 | 시나리오 세트로 2개 모델을 비교해 결정 |
| LIVE | 시나리오 통과 후 LIVE 1회, 이후 dry-run 원복 |

### 1.3 관련 문서

- 탐지·판단 정책(SoT): `C:\Users\tkdrb\project\fireware\.claude\worktrees\log-stack-fwctl\docs\detection-policy.md` v0.1
- 룰 임계치(SoT): 같은 worktree `observability/grafana/provisioning/alerting/rules.yaml`
- fwctl 계약: 같은 worktree `docs/fwctl-api.md`, 전체 흐름 `docs/runbook.md`
- MCP 게이트웨이: `C:\Users\tkdrb\project\agent\agent_mcp\mcp-firewall-server\` (`registration.json`)
- 방화벽 관리 화면: `docs/archive/2026-11/firewall-admin-console/`, 준비 절차 `docs/firewall-admin-setup.md`
- 스케줄 API: `idt/docs/api/agent-schedule.md`

### 1.4 저장소별 작업 분담

fireware `CLAUDE.md`의 분담 원칙을 따른다: MCP 서버 코드는 agent_mcp, 판단(언제 막을지)은 sangplusbot 에이전트, fireware는 정책 문서와 관측·집행 설정까지.

| 저장소 | 이번 작업 |
|---|---|
| agent_mcp | 조회 도구 2개 (TDD, mcp-shared·FastMCP 규칙) |
| sangplusbot | 알림 수신 기능, 자동 실행 건너뜀 옵션, 트리거 스크립트, 방화벽 화면 토글, 에이전트 등록 절차 |
| fireware | 정책 v0.2(주기·도구명·트리거), 웹훅 템플릿 수신 주소, runbook Phase 4 절 |

---

## 2. 범위

### 2.1 포함

- [ ] **조회 도구 (agent_mcp)**: `list_detections`(발화 알림을 출발지별로 묶음), `get_ip_context(ip)`(정책 부록 Q1~Q4 고정 쿼리)
- [ ] **자동 실행 건너뜀 옵션 (sangplusbot, 일반 기능)**: 같은 에이전트가 실행 중이거나 승인 대기 건이 있으면 그 회차를 실행하지 않고 이력에 `skipped`로 남긴다. 스케줄·알림 수신 공통, 기본 off
- [ ] **트리거 스크립트**: `idt/scripts/`에 매 분 스케줄 트리거를 호출하는 루프
- [ ] **알림 수신 기능 (sangplusbot, 일반 기능)**: Alertmanager 형식 웹훅 수신 → 즉시 202 → 백그라운드로 에이전트 실행. 에이전트별 토큰, 재전송 중복 방지, 해소(resolved) 알림 무시, 알림 → 지침문 변환. 기본 off
- [ ] **방화벽 화면 자동 점검 토글**: 상태 띠에 스케줄·알림 수신 켜짐/꺼짐, 마지막 실행 시각·결과. 관리자가 거기서 바꾼다
- [ ] **보안 에이전트 구성**: 정책에서 파생한 프롬프트(8,000자 이내) 파일, 도구 묶음, 승인 게이트, 10분 스케줄, 알림 수신 연결을 재현 가능한 절차로 등록
- [ ] **fireware 정책 v0.2·웹훅 활성화**: 주기 10분, 도구명, 웹훅 트리거·건너뜀 반영. 웹훅 템플릿을 새 수신 주소로 활성화
- [ ] **검증**: 시나리오 세트, 모델 2개 비교, LIVE 1회 후 dry-run 원복

### 2.2 제외

- mcp-grafana 등록 (F1. 필요해지면 별도 사이클)
- 에이전트의 해제(`unblock_ip`) 판단. 해제는 사람이 방화벽 화면에서 한다
- LIVE 상시 운영, 실장비 연결 (`docs/firewall-admin-setup.md` §7 조건 그대로)
- 승인 API 응답 지연(30초 초과) 해소 — 기존 플랫폼 결함, 별도 사이클
- 판단 결과를 방화벽 화면에 별도 탭으로 보여 주기. 판단 보고는 기존 실행 기록(관리자 > 에이전트 실행, 스케줄 이력)으로 본다
- 알림 수신 기능의 Alertmanager 외 형식(Datadog·PagerDuty 등)

---

## 3. 요구사항

### 3.1 기능 요구사항

**A. 조회 도구 (agent_mcp)**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-01 | `list_detections()`: Grafana 알림 API에서 `source=firewall` 이고 상태가 발화(Alerting)인 인스턴스만 가져와 `src_ip`별로 묶는다. 묶음마다 `rule_ids`·`kinds`·최고 `severity`·`action_hint`(우선순위 extend > block > report)·`lab_verified`·룰별 값·`active_at`을 준다. R06은 `dest_ip:dest_port` 키로 따로 묶는다 | High |
| FR-02 | `list_detections()`는 보호 대상 주소(fwctl 화이트리스트와 같은 목록)를 후보에서 빼고 `ignored_whitelisted`로 따로 돌려준다. 에이전트가 호출 대상으로 착각하지 않으면서 경고 보고는 할 수 있게 한다 | High |
| FR-03 | `get_ip_context(ip)`: 정책 부록 Q1(5분 포트 분포)·Q2(1시간 허용 연결 수)·Q3(샘플 20줄)·Q4(7일 **live** 차단 이력, `dry_run="false"`)를 고정 LogQL로 조회해 한 번에 돌려준다. IP는 IPv4 단일 주소만 받는다 | High |
| FR-04 | 두 도구는 읽기 전용이다. Grafana 서비스 계정(Viewer) 토큰으로 Grafana API·Loki 데이터소스 프록시만 호출하고, LLM이 쿼리 문자열을 넘기는 인자는 없다 | High |
| FR-05 | Grafana가 응답하지 않으면 `GRAFANA_UNAVAILABLE: …` 형식 오류를 낸다(재시도 없음, mcp-firewall-server 오류 형식과 동일) | Medium |

**B. 자동 실행 건너뜀 (sangplusbot, 일반 기능)**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-06 | 에이전트 자동 실행(스케줄·알림 수신)에 "실행 중이거나 승인 대기 건이 있으면 건너뜀" 옵션을 둔다. 기본 off라 기존 스케줄 동작은 바뀌지 않는다 | High |
| FR-07 | 건너뛴 회차는 스케줄 이력(또는 수신 이력)에 `skipped`와 사유(`approval_pending` / `run_in_progress`)로 남고, 다음 실행 시각은 정상적으로 계산된다 | High |
| FR-08 | 승인 저장소에 "에이전트의 대기(pending) 승인 존재 여부" 조회를 추가한다 | High |

**C. 트리거 스크립트**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| ~~FR-09~~ | ~~`idt/scripts/` 트리거 스크립트~~ — **Design v0.1에서 삭제**: 백그라운드 워커가 30초마다 스케줄 트리거를 앱 안에서 실행한다(`background_worker_enabled` 기본 true) | — |

**D. 알림 수신 (sangplusbot, 일반 기능)**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-10 | 에이전트 소유자가 에이전트별 알림 수신을 설정한다(켜기/끄기, 토큰 발급·재발급, 지침 앞머리). 토큰은 해시로 저장하고 발급 때 한 번만 보여 준다 | High |
| FR-11 | 수신 엔드포인트는 `Authorization: Bearer <token>`으로 인증하고 Alertmanager 웹훅 JSON(`status`, `groupKey`, `alerts[]`의 `labels`·`annotations`·`startsAt`·`fingerprint`·`values`)을 받는다. 인증 후 즉시 202를 돌려주고 에이전트는 백그라운드로 실행한다 | High |
| FR-12 | `status=firing` 알림만 지침문으로 바꾼다. 해소(resolved)만 있는 요청은 실행하지 않는다. 지침문은 라벨·요약·값만 담고 정해진 길이를 넘지 않는다 | High |
| FR-13 | 같은 `groupKey`와 같은 발화 fingerprint 집합이 정해진 시간 안에 다시 오면(재전송) 실행하지 않는다 | High |
| FR-14 | 수신 결과(실행 / 건너뜀 / 중복 / 해소만 / 꺼짐)를 이력으로 남긴다. FR-06 건너뜀 옵션이 여기에도 적용된다 | Medium |

**E. 방화벽 화면 자동 점검 토글 (firewall_admin 모듈)**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-15 | 설정 `FIREWALL_ADMIN_AGENT_ID`(보안 에이전트)가 있으면, 방화벽 모듈이 그 에이전트의 스케줄·알림 수신 상태(켜짐 여부, 다음·마지막 실행 시각과 결과)를 조회하는 API를 제공한다 | High |
| FR-16 | 관리자가 방화벽 화면 상태 띠에서 스케줄·알림 수신을 각각 끄고 켠다. 끌 때는 확인창을 띄운다 | High |
| FR-17 | 에이전트가 설정되지 않았거나 없으면 토글 자리에 "보안 에이전트 미설정"과 준비 절차 안내를 보여 주고, 나머지 방화벽 화면은 그대로 동작한다 | Medium |

**F. 보안 에이전트·정책 (sangplusbot + fireware)**

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| FR-18 | 정책 v0.2에서 파생한 시스템 프롬프트(8,000자 이내)를 저장소 파일로 둔다. 절차(묶기·선조회·맥락·분류·행동·보고), 유형별 행동, TTL, 쿨다운, reason 형식, 금지 사항을 담는다 | High |
| FR-19 | 에이전트 도구: `list_detections`, `get_ip_context`, `list_blocks`, `block_ip`(승인 게이트). `unblock_ip`는 주지 않는다. 승인 필요 도구는 카테고리 미분류 | High |
| FR-20 | 에이전트·스케줄(`*/10` cron)·알림 수신·건너뜀 옵션을 재현 가능한 절차(스크립트 또는 문서화된 API 호출)로 만든다 | High |
| FR-21 | fireware `detection-policy.md`를 v0.2로 올린다: 주기 10분, 조회 도구명, 웹훅 트리거, 승인 대기 건너뜀. 웹훅 템플릿 수신 주소를 FR-11 엔드포인트로 바꾸고 활성화 절차를 runbook에 적는다 | High |
| FR-22 | 실행 보고는 IP마다 한 줄(분류, 근거, 행동, fwctl 응답의 `dry_run`)로 쓰고, 후보가 없으면 짧게 끝낸다 | Medium |

### 3.2 비기능 요구사항

| 분류 | 기준 | 확인 방법 |
|------|------|-----------|
| 안전 | 에이전트가 LIVE 차단을 직접 일으킬 수 없다. `block_ip`는 승인 게이트를 거치고, fwctl이 화이트리스트·TTL 상한·dry-run을 다시 강제한다 | 시나리오 S3·S5, 승인 전 fwctl 감사에 기록 없음 |
| 보안 | 조회 도구는 Viewer 토큰·읽기 전용·고정 쿼리. 알림 수신 토큰은 해시 저장·상수 시간 비교·본문 크기 제한 | 단위 테스트, 코드 리뷰 |
| 격리 | 알림 수신·건너뜀은 기본 off. 기존 스케줄·웹훅·승인 동작 불변. 방화벽 전용 코드는 firewall_admin 모듈 안에만 | 기존 테스트 회귀, AST 계약 테스트 확장 |
| 응답 | 알림 수신은 인증 후 1초 안에 202 | 통합 테스트 |
| 비용 | 후보가 없는 회차는 도구 1회 + 짧은 답변으로 끝난다. 회차당 토큰을 측정해 기록 | 실행 기록(`ai_llm_call`) |
| 관측 | 모든 자동 실행·건너뜀·중복 무시가 이력에 남는다 | 시나리오 확인 |

---

## 4. 성공 기준

### 4.1 완료 정의 (Success Criteria)

| ID | 기준 | 확인 방법 |
|----|------|-----------|
| SC-1 | attacker 스캔 중 `list_detections`가 172.28.10.66 묶음(R02·R04·R01·R07, severity high, action_hint block)을 돌려주고, `get_ip_context`가 Q1~Q4를 돌려준다 | agent_mcp 단위 테스트 + 실측 |
| SC-2 | **S1 스캔**: 스케줄 회차에서 에이전트가 `block_ip(172.28.10.66, ttl, reason)`을 요청한다. TTL은 정책 §6(live 이력에 따라 1800 또는 3600), reason은 §9 형식. 승인 탭에 대기 건이 뜨고 승인하면 fwctl이 `dry_run:true`로 응답한다 | 실측 (dry-run) |
| SC-3 | **S2 정상**: client 정상 HTTP만 있을 때 차단 요청이 없다 | 실측 |
| SC-4 | **S3 보호 주소**: client(화이트리스트)가 관리 포트를 반복해 R04가 울려도 `block_ip`를 호출하지 않고 경고를 보고한다 | 실측 |
| SC-5 | **S4 승인 대기**: 승인 대기 건이 있는 동안 다음 스케줄 회차가 `skipped(approval_pending)`로 남는다 | 실측 |
| SC-6 | **S5 웹훅**: Grafana 알림이 수신 엔드포인트로 오면 202 후 1회 실행된다. 같은 그룹 재전송은 실행하지 않고, 해소 알림은 무시한다 | 실측 + 통합 테스트 |
| SC-7 | **S6 토글**: 방화벽 화면에서 스케줄·알림 수신을 끄면 트리거·웹훅이 실행하지 않고, 켜면 다시 실행한다 | 실측 |
| SC-8 | **모델 비교**: S1~S4를 모델 2개로 각 3회 실행해 정답 행동 비율과 회차당 토큰을 기록하고, 안전 시나리오(S3·S4)는 100%인 모델을 고른다 | 비교 표 |
| SC-9 | **LIVE 1회**: LIVE에서 S1을 승인하면 ipset에 들어가고 fwctl 감사에 `actor`가 에이전트로 남는다. 차단 중 반복(R08)이 울리면 연장 요청(TTL 3600)을 확인한다. 끝나면 dry-run 원복 | 실측 |
| SC-10 | 옵션을 켜지 않은 기존 스케줄·웹훅·승인 동작과 방화벽 모듈 off 상태가 그대로다 | 기존 테스트 회귀 0건 |

### 4.2 품질 기준

- [ ] 백엔드 pytest·프론트 Vitest·agent_mcp 테스트를 테스트 먼저 작성(TDD)
- [ ] 신규 실패 0건 (백엔드 기존 상시 실패 55건, 프론트 기존 실패, `tsc -b` 기존 211건 기준)
- [ ] 변경 파일 린트 0건
- [ ] Gap 분석 Match Rate ≥ 90%

---

## 5. 위험과 대응

| 위험 | 영향 | 가능성 | 대응 |
|------|------|--------|------|
| LLM이 정책을 잘못 적용(잘못된 TTL·보호 주소 호출·보고 대상 차단) | High | Medium | 3중 방어(승인 게이트, fwctl 화이트리스트·TTL·dry-run, 조회 도구가 보호 주소를 후보에서 뺌). 시나리오 반복 실행과 모델 비교(SC-8) |
| 승인 대기 건이 쌓이거나 웹훅·스케줄이 동시에 같은 IP를 요청 | Medium | High | 건너뜀 옵션(실행 중·승인 대기). 웹훅 재전송 중복 방지 |
| Grafana 웹훅 JSON·재전송 동작이 가정과 다름 | Medium | Medium | M3 시작 전에 Grafana 12.0 웹훅 실제 본문을 받아 픽스처로 저장하고 설계 |
| 스케줄 실행 경로(`auth_ctx` 없음)에서 MCP 도구 권한·승인 동작이 대화와 다름 (F7) | High | Medium | M2에서 실측으로 먼저 확인. 막히면 Design에 실행 주체 처리 추가 |
| 프롬프트 8,000자 제한 (F5) | Medium | High | 정책 원문은 fireware에 두고 프롬프트는 행동 규칙만 압축. 룰 표·쿼리는 도구가 대신 가진다 |
| 10분마다 LLM 호출 비용 | Low | High | 후보 없으면 즉시 종료하는 프롬프트, 회차당 토큰 측정, 토글로 끄기 |
| 방화벽 화면 토글의 소유권 (F6) | Medium | Medium | Design에서 결정: 보안 에이전트 소유자를 관리자 계정으로 고정하거나 방화벽 모듈이 관리자 권한으로 바꾸는 경로 |
| agent_mcp 미커밋 변경이 많고, fireware 작업 브랜치가 `main`에 미머지·잠김 | Medium | High | 각 저장소 커밋 범위를 Do 단계에서 사용자와 확인. fireware는 기존 worktree `log-stack-fwctl` 기준 |
| 승인 필요 MCP 도구 카테고리 함정 (F8) | High | Low | 등록 절차에 "카테고리 미분류" 명시, 시나리오 S1에서 실제 호출 확인 |
| Loki 보존 7일로 재범 이력이 7일까지만 보임 | Low | High | 정책에 명시(현행 유지) |
| 10분 사이에 발화했다 해소된 알림을 스케줄이 놓침 | Low | Medium | 알림 웹훅이 즉시 경로로 보완 |

---

## 6. 영향 분석

### 6.1 변경 자원

| 자원 | 종류 | 변경 내용 |
|------|------|-----------|
| 스케줄 테이블·이력 | DB (마이그레이션 V098~) | 건너뜀 옵션 컬럼, 이력 상태 `skipped`·사유 |
| 알림 수신 설정·이력 | DB 신규 테이블 | 에이전트별 수신 설정(토큰 해시, 켜짐, 지침 앞머리), 수신 이력(groupKey, fingerprint 해시, 결과) |
| 승인 저장소 | Repository | 에이전트별 대기 건 존재 조회 |
| 스케줄 트리거 유스케이스 | Application | 건너뜀 판정 |
| 알림 수신 API | API 신규 | 공개 수신 엔드포인트 + 소유자용 설정 API |
| firewall_admin 모듈 | API·설정 | `FIREWALL_ADMIN_AGENT_ID`, 자동 점검 조회·토글 API |
| 방화벽 화면 | 프론트 | 상태 띠 자동 점검 토글 |
| 에이전트 빌더 | 프론트 | 알림 수신 설정 패널, 스케줄 건너뜀 옵션 (일반 기능이므로 소유자가 설정) |
| `idt/scripts/` | 스크립트 신규 | 트리거 루프 |
| agent_mcp | MCP 도구 | 조회 도구 2개 |
| fireware | 문서·설정 | 정책 v0.2, 웹훅 템플릿, runbook |

### 6.2 기존 소비자

| 자원 | 동작 | 코드 경로 | 영향 |
|------|------|-----------|------|
| 스케줄 | 트리거 실행 | `trigger_due_schedules_use_case.py` | 옵션 off면 없음 |
| 스케줄 | CRUD·토글 | `agent_schedule_router.py`, `SchedulePanel.tsx` | 응답에 옵션 필드 추가 — 프론트 타입 동기화 필요 |
| 스케줄 이력 | 조회 | `list_schedule_runs_use_case.py` | 상태값 `skipped` 추가 — 화면 표시 확인 필요 |
| 승인 | 생성·조회·재개 | `run_agent_use_case.py`, `approval_router.py` | 조회 메서드 추가만, 동작 불변 |
| 공개 웹훅 | 서명 실행 | `webhook_public_router.py` | 없음 (별도 엔드포인트) |
| firewall_admin | 상태 조회 | `admin_firewall_router.py`, `useAdminNavGroups` | 에이전트 미설정이면 기존과 동일 |

### 6.3 확인 방법

- [ ] 기존 스케줄·웹훅·승인 테스트 회귀
- [ ] 백엔드 전체 회귀 실패 목록이 master와 같음
- [ ] 방화벽 모듈 off·에이전트 미설정 상태에서 기존 화면 동작

---

## 7. 아키텍처 고려사항

### 7.1 프로젝트 레벨

기존 sangplusbot 구조(Thin DDD, Enterprise 수준 레이어 분리)를 따른다. agent_mcp는 그 저장소의 TDD·Thin DDD·mcp-shared·FastMCP 규칙을 따른다.

### 7.2 주요 결정

**확정 (사용자 결정)**

| 결정 | 선택 | 근거 |
|------|------|------|
| 조회 | 고정 조회 도구 | F1. LLM이 LogQL을 쓰지 않아 결과가 예측 가능하고 도구가 적다 |
| 트리거 | 스케줄 10분 + 알림 웹훅 | 웹훅은 즉시성, 스케줄은 누락 보완 |
| 웹훅 수신 | sangplusbot 일반 기능 | F4. 서명·본문·동기 실행이 Grafana와 맞지 않음. 다른 모니터링에도 쓴다 |
| 중복 | 실행 중·승인 대기 중이면 건너뜀 | F3. 일반 옵션, 기본 off |
| 토글 | 방화벽 화면 | 운영자가 한 화면에서 감독 |

**Design에서 정할 것**

| 결정 | 후보 |
|------|------|
| 조회 도구 위치 | mcp-firewall-server에 추가 / agent_mcp 새 서버. mcp-firewall-server는 "판단 없이 fwctl 1:1" 원칙을 문서에 두고 있다 |
| 건너뜀 옵션 저장 위치 | 스케줄 단위 / 에이전트 단위(스케줄·알림 수신 공통) |
| 알림 수신 실행 방식 | 기존 백그라운드 잡 재사용 / 웹훅 유스케이스 비동기화 |
| 토글 소유권 | 보안 에이전트 소유자를 관리자로 고정 / 방화벽 모듈이 관리자 권한으로 변경 |
| 프롬프트 파일 위치 | fireware(정책 옆) / sangplusbot |
| 재현 어려운 판단(R03·R06 보고만) 확인 | 도구 응답 고정 픽스처로 1회 실행 / 범위 밖 |

### 7.3 흐름

```
[fireware]  firewall → ulogd → Alloy → Loki ← Grafana 알림 8개
                                              │ 웹훅 (Bearer, Alertmanager JSON)
[sangplusbot]                                 ▼
  알림 수신 ──202──▶ 백그라운드 실행 ─┐
  idt/scripts 트리거(매 분) → 스케줄(*/10) ─┤  건너뜀 판정(실행 중·승인 대기)
                                           ▼
                                보안 에이전트 (정책 v0.2 프롬프트)
                                  ├─ list_detections / get_ip_context ──▶ [agent_mcp 조회 도구] ──▶ Grafana API (Viewer)
                                  ├─ list_blocks
                                  └─ block_ip ──▶ 승인 게이트 ──▶ 방화벽 화면 승인 탭 (사람)
                                                               └─▶ [mcp-firewall-server] ──▶ fwctl (화이트리스트·TTL·dry-run) ──▶ ipset
  방화벽 화면 상태 띠: 자동 점검 토글 (스케줄·알림 수신 on/off)
```

---

## 8. 규칙 전제

### 8.1 기존 규칙

- sangplusbot: `CLAUDE.md` 3종, `idt/docs/rules/`(db-session, logging, testing 등), `idt/docs/rules/tool-and-mcp.md`
- 특화 vs 일반화: 알림 수신·건너뜀은 일반 기능으로, 방화벽 전용 코드는 firewall_admin 모듈 안에만 둔다(코어에 방화벽 하드코딩 금지)
- agent_mcp: 그 저장소 `CLAUDE.md` + `.claude/rules/*.md`, MCP 서버는 무상태·서버 간 직접 통신 금지
- fireware: 정책 SoT는 `detection-policy.md`, 임계치 SoT는 `rules.yaml`

### 8.2 정할 규칙

| 항목 | 현재 | 정할 것 | 우선순위 |
|------|------|---------|:--------:|
| 조회 도구 응답 형식 | 없음 | 필드명·묶음 규칙을 Design §4에 계약으로 | High |
| 알림 → 지침문 템플릿 | 없음 | 길이 상한, 포함 필드 | High |
| 이력 상태값 | 스케줄 `success`/`failed` | `skipped` + 사유 코드 | High |

### 8.3 환경변수

| 변수 | 위치 | 용도 |
|------|------|------|
| `SCHEDULER_TRIGGER_TOKEN` | `idt/.env` (기존) | 트리거 스크립트·엔드포인트 인증 |
| `FIREWALL_ADMIN_AGENT_ID` | `idt/.env` (신규) | 방화벽 화면 토글 대상 에이전트 |
| Grafana URL·토큰 | agent_mcp 조회 도구 컨테이너 | 조회 도구용 Viewer 서비스 계정 |
| `FW_ALERT_WEBHOOK_URL`·`FW_ALERT_WEBHOOK_TOKEN` | fireware `.env` (기존 템플릿) | 알림 수신 주소·토큰 |

---

## 9. 다음 단계

1. [ ] `/pdca design firewall-agent` — §7.2 미정 항목 결정, 조회 도구·알림 수신 계약, 모듈 지도
2. [ ] M2 시작 시 F7(스케줄 경로 도구 권한·승인) 실측, M3 시작 시 Grafana 웹훅 실제 본문 픽스처 확보
3. [ ] 저장소별 커밋 범위 확인 (agent_mcp 미커밋 상태, fireware 브랜치)

---

## 버전 이력

| 버전 | 날짜 | 변경 | 작성 |
|------|------|------|------|
| 0.1 | 2026-11-24 | 최초 작성. 사용자 결정 8건 반영 | 배상규 |
| 0.2 | 2026-11-24 | Design 반영: FR-09 삭제(워커가 스케줄 실행), F7 해소(소유자 ID로 도구 권한 조회) | 배상규 |
