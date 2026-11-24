# firewall-admin-console Design Document

> **Summary**: idt 백엔드에 조립 파일 하나로 켜고 끄는 `firewall_admin` 모듈을 추가해 fwctl(집행)과 Grafana(알림·로그·감사)를 대신 호출하고, idt_front `/admin/firewall`에 상태 띠 + 탭 4개 화면을 만든다. 엔드포인트 7개, DB 변경 없음.
>
> **Project**: sangplusbot (idt + idt_front) — 연동: fireware, agent_mcp
> **Author**: 배상규
> **Date**: 2026-11-23
> **Status**: Implemented (v0.6, Check 97.8%)
> **Planning Doc**: [firewall-admin-console.plan.md](firewall-admin-console.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (DB 변경 없음, §3으로 대체) |
| Phase 2 | Coding Conventions | N/A (§10으로 대체) |
| Phase 3 | Mockup | N/A (§5 화면 구성으로 대체) |
| Phase 4 | API Spec | 이 문서 §4 |

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

### 1.1 Design Goals

1. **조립 파일 한 곳으로 켜고 끈다.** `FIREWALL_ADMIN_ENABLED=false`(기본)면 라우터가 등록되지 않고 메뉴도 없다. 코어가 이 모듈을 import하는 곳은 `main.py`의 `wire_firewall_admin(app)` 한 줄이다.
2. **토큰은 서버에만 있다.** 브라우저는 idt API만 호출한다. 응답 스키마에 토큰 필드를 두지 않는다.
3. **안전장치는 fwctl이 계속 강제한다.** idt는 형식 검증(IPv4·TTL·사유)만 하고, 화이트리스트·TTL 상한·dry-run 판정은 fwctl 응답을 그대로 전달한다.
4. **사용자 식별을 끝까지 전달한다.** 수동 조작의 `actor`는 서버가 `sangplusbot/admin:<user_id>`로 채운다.
5. **장애를 분리한다.** fwctl 불통은 현황 탭에만, Grafana 불통은 탐지·감사 탭에만 영향을 준다.
6. **쿼리는 서버가 만든다.** 클라이언트는 LogQL을 보내지 않는다. 필터 값은 형식 검증을 통과한 것만 고정 템플릿에 넣는다.

### 1.2 Design Principles

- **검증과 쿼리 조립은 순수 함수.** `domain/firewall_admin`은 표준 라이브러리만 쓰고 I/O가 없다.
- **조용히 꺼지지 않는다.** 켰는데 URL·토큰이 비면 기동 warning + status `configured=false`. Grafana 응답 파싱 실패는 빈 목록이 아니라 503.
- **기존 계약을 건드리지 않는다.** 승인 API는 수정하지 않는다. `adminNav`는 그룹을 뒤에 추가하고 진입 경로는 그대로 둔다.
- **가짜 응답만으로 완료하지 않는다.** 모듈마다 실제 fwctl·Grafana 호출 1회를 Do 단계에서 실행한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 라우터 한 파일이 httpx 직접 호출, 페이지 한 파일 | 엔드포인트별 유스케이스 7개, 자원별 컴포넌트·훅 | 조립 파일 + 순수 검증·템플릿 + 서비스 2개 + 클라이언트 2개, 페이지 + 탭 4개 |
| **New Files** | ~10 | ~40 | 26 |
| **Modified Files** | 5 | 5 | 5 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Medium (검증·쿼리 조립이 라우터에 섞임) | Low | Low |
| **Recommendation** | 일회성 시연 | 실장비 운영 제품 | **기본 선택** |

**Selected**: Option C — **Rationale**: 차단 권한을 다루므로 검증과 LogQL 조립은 분리해 단위 테스트해야 한다. 엔드포인트 7개 규모에 유스케이스 7개는 과하다. 조립은 `source_viewer_di.py` 선례와 같은 형태로 둔다. (사용자 선택 2026-11-23)

### 2.1 Component Diagram

```
 브라우저 (admin)
   │  /admin/firewall  ── AdminRoute + AdminLayout
   │  JWT
   ▼
 idt  /api/v1/admin/firewall/*          [등록 조건: FIREWALL_ADMIN_ENABLED=true]
 ┌──────────────────────────────────────────────────────────────┐
 │ admin_firewall_router  (require_role("admin"), 오류 → HTTP)   │
 │        │                         │                           │
 │        ▼                         ▼                           │
 │ FirewallControlService     FirewallObservabilityService      │
 │  status/list/block/unblock   alerts/events/audit             │
 │        │      ▲                  │      ▲                    │
 │        │      └── domain: validation.py   logql.py (순수)    │
 │        ▼                         ▼                           │
 │ FwctlClient (httpx)        GrafanaClient (httpx)             │
 └────────┼─────────────────────────┼───────────────────────────┘
          │ Bearer + X-Request-Id   │ Bearer(서비스 계정, Viewer)
          ▼                         ▼
   fwctl :8070 ──► ipset      Grafana :3000 ──► 알림 룰 / Loki(데이터소스 프록시)

 승인 탭 ──► 기존 /api/v1/approvals (무변경) ──► tool_id 접미로 프론트 필터
```

### 2.2 Data Flow

**수동 차단**
```
폼(ip, ttl, reason) → 확인창(모드 재표시) → POST /admin/firewall/blocks
 → router: admin 확인 → request_id 생성
 → ControlService.block: validate_block_request()  [형식 오류 → 422]
 → FwctlClient.block(ip, ttl, reason, actor="sangplusbot/admin:<user_id>", request_id)
     201 → BlockResult(dry_run, expires_at, request_id)
     403 → FORBIDDEN_WHITELIST 그대로 / 422 → INVALID_TTL / 401 → FWCTL_AUTH_FAILED …
 → 구조화 로그 1건(user_id, ip, ttl, dry_run, request_id — 토큰 없음)
 → 프론트: dry_run이면 "실제로 차단되지 않았습니다", blocks 쿼리 무효화
```

**탐지·감사 조회**
```
GET /admin/firewall/alerts → GrafanaClient.rules() → firewall-detection 그룹 파싱
   → 룰 8개 + 인스턴스(상태 정규화) → 발화·대기 우선 정렬
GET /admin/firewall/events?range=1h&action=drop
   → validate_events_query() → logql.top_sources(query) / logql.recent_events(query)
   → GrafanaClient.loki_query / loki_query_range → 파싱
GET /admin/firewall/audit?range=24h&event=block&ip=…&actor=…
   → validate_audit_query() → logql.audit(query) → loki_query_range → 파싱
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `admin_firewall_router` | 두 서비스, `require_role` | HTTP 변환·오류 매핑 |
| `FirewallControlService` | `FwctlPort`, `validation` | 현황·차단·해제 |
| `FirewallObservabilityService` | `GrafanaPort`, `logql`, `validation` | 알림·로그·감사 |
| `FwctlClient` / `GrafanaClient` | httpx `AsyncClient`(앱 수명 1개씩) | 외부 호출 |
| `firewall_admin_di` | `config.settings`, 위 전부 | 조립·라우터 등록·종료 시 클라이언트 close |
| `AdminFirewallPage` | `useFirewall*` 훅, 기존 `useApprovals` 계열 | 화면 |

---

## 3. Data Model

DB 테이블은 없다. 전달 객체만 정의한다.

### 3.1 Entity Definition

```python
# domain/firewall_admin/models.py — frozen dataclass
BlockRequest(ip: str, ttl_seconds: int | None, reason: str)
BlockEntry(ip, ttl_remaining_seconds: int, packets: int, bytes: int)
BlockResult(ip, ttl_seconds, expires_at: datetime, reason, dry_run: bool, request_id)
UnblockResult(ip, removed: bool, dry_run: bool | None, already_absent: bool)
FwctlHealth(reachable: bool, dry_run: bool | None, max_ttl_seconds: int | None,
            ipset_exists: bool | None, version: str | None)
AlertInstance(src_ip: str | None, state: AlertState, active_at: datetime | None, value: str | None)
AlertRule(uid, name, rule_id, kind, severity, action_hint, state: AlertState,
          description, last_evaluation: datetime | None, instances: tuple[AlertInstance, ...])
SourceCount(src_ip: str, count: int)
FirewallEvent(ts: datetime, action, src_ip, dest_ip, protocol: int | None, dport: int | None)
AuditRecord(ts, request_id, event, actor, ip, ttl_seconds, reason, result, status, error_code, dry_run)
```

`AlertState = "firing" | "pending" | "normal" | "nodata" | "error"` — Grafana 원문 상태를 아래 표로 정규화한다.

| Grafana 원문 (실측 12.0.0) | 정규화 |
|---|---|
| `Alerting`, 룰 `state: firing` | `firing` |
| `Pending`, 룰 `state: pending` | `pending` |
| `Normal`, 룰 `state: inactive` | `normal` |
| `Normal (NoData)`, `NoData` | `nodata` |
| `Error`, `Normal (Error)`, 룰 `health != ok` | `error` |
| 그 밖 | `error` (warning 로그) |

구현에서 추가한 전달 객체(구현 기준): `BlockList`(목록 + dry_run), `LokiSample`·`LokiLine`(Grafana 응답 1건), `EventsQuery`·`AuditQuery`(검증을 통과한 조회 조건 — LogQL 템플릿은 이것만 받는다), `ALERT_STATE_ORDER`(정렬 순서). 서비스 결과 뷰는 `FirewallStatus`·`AlertsView`·`EventsView`·`AuditView`.

### 3.2 Entity Relationships

```
[수동 차단 요청] 1 ── 1 [fwctl 감사 레코드]  (request_id 로 연결, actor=sangplusbot/admin:<user_id>)
[AlertRule] 1 ── N [AlertInstance]            (src_ip 별)
[AlertInstance.src_ip] ·· [BlockEntry.ip]     (화면에서 "차단 중" 표시용 대조, 저장 관계 아님)
```

### 3.3 Database Schema

해당 없음. 마이그레이션 0건.

---

## 4. API Specification

공통: 접두 `/api/v1/admin/firewall`, 전부 `require_role("admin")`(무토큰 401, 비관리자 403). 모듈이 꺼져 있으면 전 경로 404. 오류 본문은 `{"detail": {"code", "message", "request_id"?, "details"?}}`.

### 4.1 Endpoint List

| Method | Path | Description | 외부 호출 |
|--------|------|-------------|-----------|
| GET | `/status` | 모듈·fwctl·Grafana 상태 | fwctl `GET /healthz` |
| GET | `/blocks` | 차단 목록 | fwctl `GET /v1/blocks` |
| POST | `/blocks` | 수동 차단 | fwctl `POST /v1/blocks` |
| DELETE | `/blocks/{ip}` | 해제 | fwctl `DELETE /v1/blocks/{ip}` |
| GET | `/alerts` | 탐지 룰 상태 | Grafana rules API |
| GET | `/events` | 차단 로그 집계·최근 건 | Grafana → Loki |
| GET | `/audit` | fwctl 감사 이력 | Grafana → Loki |

### 4.2 Detailed Specification

#### `GET /status`

항상 200. 외부 장애를 오류로 올리지 않고 필드로 알린다.

```json
{
  "enabled": true,
  "fwctl": {"configured": true, "reachable": true, "dry_run": true,
            "max_ttl_seconds": 3600, "ipset_exists": true, "version": "0.1.0"},
  "grafana": {"configured": true, "dashboard_url": "http://127.0.0.1:3000/d/fireware-firewall-lab"},
  "default_ttl_seconds": 600
}
```
- fwctl 불통·타임아웃: `reachable=false`, 나머지 `null`
- fwctl 503(ipset 없음): `reachable=true`, `ipset_exists=false`
- `grafana.configured`는 URL·토큰 유무만 본다(호출하지 않는다). `dashboard_url`은 설정된 Grafana URL + 고정 경로이며 토큰을 담지 않는다
- `default_ttl_seconds`는 폼 초기값(상수 600). `max_ttl_seconds`를 넘으면 max로 낮춘다

#### `GET /blocks`

```json
{"items":[{"ip":"172.28.10.66","ttl_remaining_seconds":583,"packets":12,"bytes":720}],
 "count":1,"dry_run":false}
```

#### `POST /blocks`

**Request**
```json
{"ip":"172.28.10.66","ttl_seconds":600,"reason":"R02 포트 스캔, 5분 41건"}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `ip` | 예 | IPv4 단일 주소. 앞뒤 공백 제거 후 `ipaddress.IPv4Address` 파싱 |
| `ttl_seconds` | 아니오 | 정수 `1..3600`. 생략하면 fwctl 기본값(600) |
| `reason` | 예 | 공백 제거 후 1~500자 |

`actor` 필드는 스키마에 없다(`extra="forbid"`). 서버가 `sangplusbot/admin:<user_id>`로 채운다.

**Response (201)**
```json
{"ip":"172.28.10.66","ttl_seconds":600,"expires_at":"2026-11-23T12:10:01Z",
 "reason":"…","dry_run":true,"request_id":"adm-17-3f2a…"}
```

**Errors**: §6.1

#### `DELETE /blocks/{ip}`

```json
{"ip":"172.28.10.66","removed":true,"dry_run":false,"already_absent":false,
 "request_id":"adm-17-9c1e…"}
```
fwctl 404는 200 + `removed=false, already_absent=true, dry_run=null`. 경로의 ip 형식 오류는 422 `INVALID_IP`.

fwctl의 DELETE는 본문이 없어 감사 행에 `actor`가 남지 않는다(계약 v0.1.0, 구현 중 확인). 해제한 사용자를 찾을 수 있도록 응답과 감사에 남는 요청 ID에 사용자 ID를 싣는다(§4.3).

#### `GET /alerts`

```json
{"rules":[{
   "uid":"fw-r02-port-scan","name":"R02 Vertical Port Scan","rule_id":"R02",
   "kind":"port_scan","severity":"high","action_hint":"block","state":"firing",
   "description":"…","last_evaluation":"2026-11-23T11:39:50Z",
   "instances":[{"src_ip":"172.28.10.66","state":"firing","active_at":"2026-11-23T11:31:50Z","value":"41"}]}],
 "firing_count":1,"fetched_at":"2026-11-23T11:40:02Z"}
```
- 그룹 `firewall-detection`의 룰 전부(현재 8개). 그룹이 없으면 503 `GRAFANA_UNAVAILABLE`(빈 목록 아님)
- 정렬: 룰은 `firing` → `pending` → `error` → 나머지, 같은 상태 안에서는 `rule_id` 순. 인스턴스도 같은 순서
- `nodata`·`normal` 인스턴스는 룰당 최대 5개까지만 싣는다(발화가 끝난 과거 IP 누적 방지)
- `firing_count`는 발화 중인 **인스턴스** 수다(룰 수가 아니다). 탐지 탭 배지에 쓴다
- annotation `summary`는 Grafana가 템플릿 원문(`{{ $labels.src_ip }}`)으로 돌려주므로 쓰지 않는다. `description`만 싣는다

#### `GET /events`

Query: `range` ∈ `15m|1h|6h|24h`(기본 `1h`), `action` ∈ `all|drop|block`(기본 `all`), `limit` 1~200(기본 50)

```json
{"range":"1h","action":"all",
 "top_sources":[{"src_ip":"172.28.10.66","count":182}],
 "recent":[{"ts":"2026-11-23T11:39:41Z","action":"drop","src_ip":"172.28.10.66",
            "dest_ip":"172.28.20.10","protocol":6,"dport":22}],
 "fetched_at":"…"}
```
`top_sources`는 상위 10개. `dport`는 로그의 `dest_port`다(실측: ulogd JSON은 TCP·UDP 모두 `src_port`·`dest_port` 키를 쓴다. ICMP는 `null`).

#### `GET /audit`

Query: `range` ∈ `1h|6h|24h|7d`(기본 `24h`), `event` ∈ `all|block|unblock`(기본 `all`), `ip`(선택, IPv4), `actor`(선택, `^[A-Za-z0-9._:/-]{1,100}$` + 영숫자 1자 이상 — `.*` 같은 정규식 조각 거부, 부분 일치), `limit` 1~200(기본 100)

```json
{"range":"24h","items":[{"ts":"…","request_id":"3f2a…","event":"block",
   "actor":"sangplusbot/admin:17","ip":"172.28.10.66","ttl_seconds":600,
   "reason":"…","result":"ok","status":201,"error_code":null,"dry_run":true}],
 "count":1,"fetched_at":"…"}
```
`list`·`health` 이벤트는 폴링으로 대량 발생하므로 `event=all`에서도 제외한다(`block`·`unblock`만).

### 4.3 fwctl 호출 규약

- 계약: fireware `docs/fwctl-api.md` v0.1.0. 변경하지 않는다
- 헤더: `Authorization: Bearer <FIREWALL_ADMIN_FWCTL_TOKEN>`, `X-Request-Id: adm-<user_id>-<난수 24자>`, POST는 `Content-Type: application/json`
- 타임아웃 5초, 재시도 없음. httpx `AsyncClient` 1개를 앱 수명 동안 재사용
- `actor`: `f"sangplusbot/admin:{user.id}"` (100자 이내 보장)
- 토큰이 비어 있으면 요청을 보내지 않고 `FWCTL_AUTH_FAILED`

### 4.4 Grafana 호출 규약 (2026-11-23 실측, Grafana 12.0.0)

| 용도 | 요청 | 응답에서 쓰는 것 |
|---|---|---|
| 알림 룰 | `GET /api/prometheus/grafana/api/v1/rules` | `data.groups[name=="firewall-detection"].rules[]` → `uid`, `name`, `state`, `health`, `labels{rule_id,kind,severity,action_hint}`, `annotations.description`, `lastEvaluation`, `alerts[]{labels.src_ip, state, activeAt, value}` |
| Loki 순간 쿼리 | `GET /api/datasources/proxy/uid/loki/loki/api/v1/query?query=…&time=<ns>` | `data.resultType=="vector"`, `result[]{metric.src_ip, value[1]}` |
| Loki 범위 쿼리 | `GET /api/datasources/proxy/uid/loki/loki/api/v1/query_range?query=…&start=<ns>&end=<ns>&limit=N&direction=backward` | `data.resultType=="streams"`, `result[].values[][ts_ns, line]` — `line`은 원본 JSON 한 줄 |

- 헤더: `Authorization: Bearer <FIREWALL_ADMIN_GRAFANA_TOKEN>` (서비스 계정, Viewer 역할)
- 타임아웃 10초, 재시도 없음
- 데이터소스 uid는 프로비저닝 값 `loki` 고정(상수)
- 실측 메모: 7일 범위 쿼리는 빈 결과에서도 1.6초가 걸렸다(분할 169개). 감사 탭 기본 범위를 24h로 둔 이유다
- Viewer 서비스 계정 토큰으로 위 3개 경로가 모두 200임을 실측했다(2026-11-23, 계정 `sangplusbot-firewall-admin`). 응답은 `idt/tests/fixtures/firewall_admin/`에 픽스처로 저장했다

### 4.5 LogQL 템플릿 (`domain/firewall_admin/logql.py`)

값이 들어가는 자리는 `{}`로 표시한다. 들어가는 값은 전부 검증을 통과한 것뿐이다.

| 함수 | 템플릿 |
|---|---|
| `top_sources(query: EventsQuery)` | `topk(10, sum by (src_ip) (count_over_time({SEL} \| json \| __error__="" [{range}])))` |
| `recent_events(query: EventsQuery)` | `{SEL}` (선택자만. 줄 본문 JSON은 서버가 파싱한다) |
| `audit(query: AuditQuery)` | `{job="fwctl", action=~"{EV}"}`. 필터가 있을 때만 `\| json \| __error__=""` + `\| ip="{ip}"` · `\| actor=~".*{actor}.*"` |

- `SEL`: `all` → `{job="firewall", action=~"drop|block"}`, `drop`/`block` → `{job="firewall", action="<값>"}`
- `EV`: `all` → `block|unblock`, 그 외 해당 값
- `range`: 허용 목록에서 고른 문자열만
- `ip`: `ipaddress` 정규화 결과(숫자와 점뿐)
- `actor`: 허용 문자 정규식을 통과한 값에서 정규식 메타문자 `.`을 `\\.`로 이스케이프
- `{job="firewall", action="accept"}`(LAB_ACCEPT 신규 연결 로그)는 조회 대상에서 제외한다

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
/admin/firewall                                   (AdminLayout, 그룹 "보안 운영")
┌──────────────────────────────────────────────────────────────────────────┐
│ 방화벽                                             [Grafana 대시보드 ↗]   │
├──────────────────────────────────────────────────────────────────────────┤
│ 상태 띠  ● fwctl 연결됨  [DRY-RUN]  TTL 상한 3600초  ipset 정상  v0.1.0    │
│          (DRY-RUN이면: "차단 요청은 기록만 되고 실제로 적용되지 않습니다")   │
├──────────────────────────────────────────────────────────────────────────┤
│ [현황] [탐지 ●1] [감사] [승인 2]                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ 현황 탭                                                                   │
│  ┌ IP 차단 ──────────────────────────────────────────────────────────┐   │
│  │ IP [____________]  유지 시간 [600]초  사유 [____________________] │   │
│  │                                                     [차단 요청]   │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│  현재 차단 목록 (1)                                    10초마다 갱신       │
│  IP              남은 시간    패킷     바이트                              │
│  172.28.10.66    9분 43초     12      720             [해제]             │
└──────────────────────────────────────────────────────────────────────────┘
 탐지 탭: 룰 표(상태·룰·심각도·권고·출발지 IP·시작 시각·[이 IP 차단])
          + 기간/구분 선택 + 출발지 Top 10 + 최근 차단 로그 표
 감사 탭: 기간·이벤트·IP·수행자 필터 + 이력 표 ("최근 7일까지 조회됩니다")
 승인 탭: block_ip·unblock_ip 승인 대기 카드 + [승인] [거절]
```

### 5.2 User Flow

```
관리자 메뉴 → 보안 운영 > 방화벽
 ├─ 상태 띠에서 모드 확인
 ├─ 탐지 탭: 발화 룰 확인 → [이 IP 차단] → 현황 탭 폼에 IP·사유 초안 채워짐
 ├─ 현황 탭: 폼 확인 → [차단 요청] → 확인창 → 결과 안내 → 목록 갱신
 ├─ 현황 탭: [해제] → 확인창 → 목록에서 제거
 ├─ 감사 탭: 방금 조작 행 확인(수행자 = sangplusbot/admin:<내 ID>)
 └─ 승인 탭: 에이전트 요청 건 내용 확인 → 승인/거절
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `AdminFirewallPage` | `src/pages/AdminFirewallPage/index.tsx` | status 조회, 꺼짐 안내, 상태 띠, 탭 전환, 차단 폼 초안 상태 보유 |
| `FirewallStatusBar` | `…/FirewallStatusBar.tsx` | 연결·모드 배지·TTL 상한·ipset·버전 |
| `FirewallBlocksTab` | `…/FirewallBlocksTab.tsx` | 차단 폼 + 목록 + 해제 |
| `BlockIpForm` | `…/BlockIpForm.tsx` | 입력·클라이언트 검증·확인창·결과 안내 |
| `FirewallDetectionTab` | `…/FirewallDetectionTab.tsx` | 룰 표, Top 10, 최근 로그 |
| `FirewallAuditTab` | `…/FirewallAuditTab.tsx` | 필터 + 이력 표 |
| `FirewallApprovalsTab` | `…/FirewallApprovalsTab.tsx` | 승인 대기 건 필터·표시·처리 |
| `firewallService` | `src/services/firewallService.ts` | API 7개 호출 |
| `useFirewall` 훅 묶음 | `src/hooks/useFirewall.ts` | `useFirewallStatus`·`useFirewallBlocks`·`useBlockIp`·`useUnblockIp`·`useFirewallAlerts`·`useFirewallEvents`·`useFirewallAudit`·`useFirewallApprovals`, 보조 함수 `firewallErrorMessage`·`firewallToolName`. 메뉴용은 `src/hooks/useAdminNavGroups.ts` |
| 타입·상수 | `src/types/firewall.ts` | 응답 타입, `FIREWALL_TABS`, range 목록, `FIREWALL_APPROVAL_TOOL_SUFFIXES` |
| 재사용 | `components/common/`, `components/ui/`, `pages/JobsPage/` | `LoadingButton`, `ConfirmDialog`, `ui/Badge`·`ui/Button`·`ui/Tabs`, 거절 사유 창 `RejectReasonDialog`(작업함 페이지 폴더에서 직접 import — 페이지 간 결합이므로 `components/`로 옮기는 것은 후속 후보) |

### 5.4 Page UI Checklist

#### 공통 (페이지 머리·상태 띠)

- [x] 제목 "방화벽"
- [x] 링크: "Grafana 대시보드" — `status.grafana.dashboard_url`이 있을 때만, 새 탭
- [x] 모듈 꺼짐(status 404): 안내 문구 "방화벽 관리 기능이 꺼져 있습니다"와 설정 이름 `FIREWALL_ADMIN_ENABLED` 표시, 탭·폼 미표시
- [x] 배지: 연결 상태 — "연결됨"(초록) / "연결 안 됨"(빨강) / "설정 필요"(회색, `configured=false`)
- [x] 배지: 모드 — "DRY-RUN"(노랑) / "LIVE"(빨강). 색과 글자 함께
- [x] 문구: DRY-RUN일 때 "차단 요청은 기록만 되고 실제로 적용되지 않습니다"
- [x] 표시: TTL 상한(초), ipset 상태(정상/없음), fwctl 버전
- [x] 탭 4개: 현황 / 탐지(발화 건수 배지) / 감사 / 승인(대기 건수 배지)

#### 현황 탭

- [x] 입력: IP (필수, IPv4 형식 검증 메시지)
- [x] 입력: 유지 시간(초) (숫자, 기본 `default_ttl_seconds`, 범위 1~`max_ttl_seconds`, 범위 안내 문구)
- [x] 입력: 사유 (필수, 최대 500자, 글자 수 표시)
- [x] 버튼: "차단 요청" (`LoadingButton`, fwctl 불통·검증 실패 시 비활성)
- [x] 확인창: 모드·IP·유지 시간·사유 재표시. LIVE면 "실제 트래픽이 차단됩니다" 경고
- [x] 결과 안내: 성공 + `dry_run=true` → "실제로 차단되지 않았습니다(DRY-RUN)" / 성공 + `false` → "차단했습니다. 만료: {시각}"
- [x] 오류 안내: `FORBIDDEN_WHITELIST` → "보호 대상 주소라 차단할 수 없습니다", `FWCTL_AUDIT_ERROR` → "차단은 적용됐지만 감사 기록에 실패했습니다. 운영자에게 알려 주세요", 그 밖 코드별 문구(§6.1)
- [x] 표: 차단 목록 — IP, 남은 시간(분·초, 1초 단위 감소), 패킷, 바이트, [해제]
- [x] 표시: 건수, "10초마다 갱신"
- [x] 빈 상태: "차단 중인 IP가 없습니다"
- [x] 버튼: 행별 "해제" (`LoadingButton`) → 확인창 → 결과(`already_absent`면 "이미 해제된 주소입니다")
- [x] 탐지 탭에서 넘어온 초안: IP·사유가 채워지고 폼으로 포커스 이동

#### 탐지 탭

- [x] 표: 룰 8개 — 상태 배지(발화/대기/정상/데이터 없음/오류), 룰 ID·이름, 심각도(high/medium), 권고(차단/보고/연장)
- [x] 룰 행 펼침: 출발지 IP별 인스턴스 — IP, 상태, 시작 시각, "차단 중" 표시(현재 차단 목록과 대조. 버튼 자리에 나오므로 발화·대기 인스턴스에만 표시한다 — 과거 출발지는 조치 대상이 아니다). 발화·대기 룰은 항상 펼쳐 둔다. 인스턴스의 `value`는 표시하지 않는다(실측에서 건수가 아니라 임계 조건식 결과 `1`이었다)
- [x] 버튼: 인스턴스별 "이 IP 차단" — 발화·대기 중인 인스턴스에만 표시. `action_hint=report` 룰, `src_ip` 없는 인스턴스, 발화가 끝난 과거 출발지(정상·데이터 없음)에는 표시하지 않음. 사유 초안은 "{룰 이름} 탐지"
- [x] 정렬: 발화 → 대기 → 오류 → 나머지
- [x] 선택: 기간(15분/1시간/6시간/24시간), 구분(전체/정책 차단 drop/차단 목록 block)
- [x] 목록: 출발지 Top 10 — IP, 건수, 막대, "이 IP 차단"
- [x] 표: 최근 차단 로그 — 시각, 구분, 출발지, 목적지, 포트, 프로토콜(TCP/UDP/ICMP 표기)
- [x] 갱신: 30초 간격 + 새로고침 버튼
- [x] 오류 상태: `GRAFANA_UNAVAILABLE` → "Grafana에서 정보를 가져올 수 없습니다. Grafana가 실행 중인지 확인하세요." + Grafana 설정 안내
- [x] 빈 상태: "선택한 기간에 차단 로그가 없습니다"

#### 감사 탭

- [x] 필터: 기간(1시간/6시간/24시간/7일), 이벤트(전체/차단/해제), IP, 수행자
- [x] 표: 시각, 이벤트, 수행자, IP, 유지 시간, 사유, 결과(성공/거부/오류 + 오류 코드), DRY-RUN 여부, 요청 ID(축약, 복사)
- [x] 문구: "최근 7일까지 조회됩니다"
- [x] 표시: 수행자가 `sangplusbot/admin:`으로 시작하면 "관리자", `mcp-firewall-server`로 시작하면 "에이전트" 구분 표시. actor가 없는 건(해제)은 요청 ID `adm-<user_id>-…`에서 관리자 ID를 읽어 표시
- [x] 동작: 기간·이벤트는 바꾸면 바로 조회, IP·수행자는 "조회" 버튼을 눌러야 반영. 캐시된 값을 쓰지 않고 매번 새로 조회(`staleTime: 0`)
- [x] 오류·빈 상태 문구

#### 승인 탭

- [x] 목록: 승인 대기 건 중 `tool_id`가 `block_ip`·`unblock_ip`로 끝나는 것 — 에이전트 이름, 도구, 초안 미리보기, 요청 시각, 만료 시각
- [x] 버튼: "승인", "거절" (`Button`의 `isPending`, 기존 승인 API). 거절은 기존 `RejectReasonDialog`로 사유를 받는다. 이미 처리된 건(409)은 안내 후 목록을 다시 불러온다
- [x] 조회: 상태 `pending`만, 한 번에 100건. 대기 건이 그보다 많으면 일부만 확인했다고 알린다
- [x] 링크: "작업함에서 보기"(상세·수정 승인은 기존 화면)
- [x] 빈 상태: "승인 대기 중인 차단 요청이 없습니다" + 연동 준비 안내(MCP 서버 등록, `block_ip` 승인 필요 지정)
- [x] 문구: "내가 소유한 에이전트의 요청만 표시됩니다"

---

## 6. Error Handling

### 6.1 Error Code Definition

| HTTP | code | 원인 | 화면 문구 |
|------|------|------|-----------|
| 401 / 403 | (기존 인증 오류) | 무토큰 / admin 아님 | 기존 처리 |
| 404 | — | 모듈 꺼짐(라우터 미등록) | "방화벽 관리 기능이 꺼져 있습니다" |
| 422 | `INVALID_IP` | IPv4 단일 주소 아님 (idt 검증 또는 fwctl 400) | "IPv4 주소 한 개를 입력하세요" |
| 422 | `INVALID_TTL` | 범위 밖 (idt 검증 또는 fwctl 422) | "유지 시간은 1~{max}초입니다" |
| 422 | `INVALID_REASON` | 사유 비었거나 500자 초과 | "사유를 1~500자로 입력하세요" |
| 422 | `INVALID_FILTER` | range·event·action·actor 형식 오류 | "조회 조건이 올바르지 않습니다" |
| 422 | `INVALID_REQUEST` | 본문이 JSON이 아님, 받지 않는 필드(`actor` 등) 포함 | "요청 형식이 올바르지 않습니다" |
| 403 | `FORBIDDEN_WHITELIST` | fwctl 403 | "보호 대상 주소라 차단할 수 없습니다" |
| 502 | `FWCTL_AUTH_FAILED` | 토큰 미설정 / fwctl 401 | "fwctl 인증에 실패했습니다. 서버 설정을 확인하세요" |
| 502 | `FWCTL_AUDIT_ERROR` | fwctl 500 `AUDIT_ERROR` | "차단은 적용됐지만 감사 기록에 실패했습니다. 운영자에게 알려 주세요" |
| 502 | `FWCTL_UNAVAILABLE` | 연결 실패, fwctl 5xx 기타, 비JSON·계약 불일치 | "fwctl에 연결할 수 없습니다" |
| 504 | `FWCTL_TIMEOUT` | 5초 초과 | "fwctl 응답이 지연되고 있습니다" |
| 503 | `GRAFANA_UNAVAILABLE` | 미설정, 연결 실패, 401/403, 타임아웃, 응답 형식 불일치, 룰 그룹 없음 | "Grafana에서 정보를 가져올 수 없습니다. Grafana가 실행 중인지 확인하세요" (탐지·감사 탭 공용) |

fwctl 응답 매핑(`FwctlClient`):

| fwctl | 결과 |
|---|---|
| 200/201 | 정상 |
| 400 `INVALID_IP` | `INVALID_IP` |
| 400 그 밖(`MISSING_FIELD`·`INVALID_JSON`) | `FWCTL_UNAVAILABLE` + warning `fwctl.contract_drift` (idt가 먼저 걸러야 하는 값) |
| 401 | `FWCTL_AUTH_FAILED` |
| 403 `FORBIDDEN_WHITELIST` | `FORBIDDEN_WHITELIST` (`details.matched` 전달) |
| 404 (DELETE) | `already_absent=true` 정상 결과 |
| 422 `INVALID_TTL` | `INVALID_TTL` (`details.max_ttl_seconds` 전달) |
| 500 `AUDIT_ERROR` | `FWCTL_AUDIT_ERROR` |
| 500 그 밖, 503(healthz 제외) | `FWCTL_UNAVAILABLE` |
| 타임아웃 / 연결 오류 | `FWCTL_TIMEOUT` / `FWCTL_UNAVAILABLE` |

`/status`만 예외로, fwctl 장애를 오류로 올리지 않고 `reachable=false`로 돌려준다.

형이 틀린 입력(`ttl_seconds:"600"`, `reason:5`, `limit=abc` 등)은 도메인 검증 전에 FastAPI가 막는다. 이 라우터는 전용 `route_class`로 그 오류를 같은 코드 형식으로 바꾼다 — 본문 `ip`→`INVALID_IP`, `ttl_seconds`→`INVALID_TTL`, `reason`→`INVALID_REASON`, 쿼리 파라미터→`INVALID_FILTER`, 그 밖→`INVALID_REQUEST` (`details.field`에 위치). 앱 전역 검증 오류 처리는 바꾸지 않는다 (Check G1).

### 6.2 Error Response Format

```json
{"detail":{"code":"FORBIDDEN_WHITELIST","message":"보호 대상 주소라 차단할 수 없습니다",
           "request_id":"3f2a…","details":{"matched":"172.28.10.10/32"}}}
```
프론트는 `ApiError(message, status, code)`의 `code`로 분기한다(`err.response`는 쓰지 않는다).

### 6.3 기동·조립

| 조건 | 동작 |
|---|---|
| `FIREWALL_ADMIN_ENABLED=false` | 조립하지 않음. 라우터 미등록. 로그 없음 |
| enabled, fwctl URL 또는 토큰 비어 있음 | 라우터 등록. warning 1회 `firewall_admin: fwctl not configured`. status `fwctl.configured=false`, 차단 계열은 `FWCTL_AUTH_FAILED` |
| enabled, Grafana URL 또는 토큰 비어 있음 | 라우터 등록. warning 1회. status `grafana.configured=false`, 조회 계열은 `GRAFANA_UNAVAILABLE` |
| enabled (설정 여부와 무관) | info 1회 `firewall_admin enabled`(URL만 기록, 토큰 제외). 미설정이면 위 warning이 함께 남는다 |
| 조립 중 예외 | warning 후 라우터 미등록. 앱 기동은 계속 |
| 앱 종료 | 두 httpx 클라이언트 `aclose()` |

---

## 7. Security Considerations

- [x] **권한**: 라우터 수준 `dependencies=[Depends(require_role("admin"))]`. 엔드포인트별 누락이 생기지 않도록 라우터에 건다. 테스트는 7개 경로 전부에 대해 일반 사용자 403을 확인
- [x] **토큰 비노출**: 응답 스키마에 토큰 필드 없음. 로그에는 URL·request_id만. 토큰은 어떤 로그에도 남기지 않는다(조립 info 로그는 URL만, 클라이언트는 요청 헤더에만 사용). `Settings` 전반을 마스킹하는 장치는 코드베이스에 없으므로 "쓰지 않는 것"으로 보장한다
- [x] **actor 위조 방지**: 요청 스키마 `extra="forbid"`, `actor`는 서버가 생성
- [x] **LogQL 주입 방지**: §4.5. 테스트 입력 — `"} | line_format`, `` ` ``, `"`, `|`, `{`, 개행, 정규식 `.*`
- [x] **경로 주입 방지**: `DELETE /blocks/{ip}`의 ip는 `IPv4Address` 파싱 결과 문자열만 fwctl 경로에 넣는다
- [x] **SSRF 없음**: 호출 대상 URL은 서버 설정 고정값. 클라이언트 입력이 URL이 되지 않는다
- [x] **XSS**: 사유·actor 등 외부 문자열은 React 텍스트로만 렌더링(HTML 삽입 없음)
- [x] **오조작 방지**: 확인창, 모드 배지, TTL 필수 상한, 모드 전환 UI 없음
- [x] **감사**: fwctl 감사(무기한 파일, Loki 7일) + idt 구조화 로그(user_id·ip·ttl·dry_run·request_id)
- [x] **최소 권한**: Grafana 서비스 계정은 Viewer
- [ ] **전송 암호화 없음**: 로컬 루프백 한정. 실장비 연결 조건(Plan §1.4)
- [ ] **호출자별 fwctl 토큰 없음**: MCP 서버와 같은 토큰 공유. Plan §1.4
- [ ] **요청 빈도 제한 없음**: admin 소수 사용. 필요해지면 추가

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L0: 단위(백엔드) | `validation`, `logql`, 두 서비스(가짜 포트), 두 클라이언트(`httpx.MockTransport`) | pytest (`uv run python -m pytest`) | Do |
| L0: 계약 | 모듈 격리 AST import 테스트, 조립 on/off | pytest | Do |
| L1: API | 라우터 7개 경로 — 권한·상태코드·응답 형태 | pytest `TestClient` | Do |
| L1-실측 | 실제 fwctl dry-run 왕복, 실제 Grafana 3개 호출 | `FIREWALL_ADMIN_LIVE=1 python -m pytest tests/integration/test_firewall_admin_live.py` (기본 실행에서는 건너뜀) | Do |
| L2: UI | 페이지·탭·폼·확인창 | Vitest + RTL + MSW | Do |
| L3: E2E | 브라우저에서 차단 → 감사 확인 | 수동(Chrome) | Check |

### 8.2 L0·L1 백엔드 테스트 시나리오

| # | 대상 | 시나리오 | 기대 |
|---|---|---|---|
| 1 | `validate_block_request` | 정상 / ` 1.2.3.4 ` / `1.2.3.0/24` / `::1` / `example.com` / 빈 값 | ok / 정규화 ok / `INVALID_IP` ×4 |
| 2 | 〃 | ttl 생략 / 1 / 3600 / 0 / 3601 / `"600"` / `true` | None / ok ×2 / `INVALID_TTL` ×4 |
| 3 | 〃 | reason 빈 값 / 공백만 / 500자 / 501자 | `INVALID_REASON` ×2 / ok / `INVALID_REASON` |
| 4 | `validate_audit_query` | range `8d` / event `list` / actor `a"b` / actor 101자 / ip `1.2.3` | `INVALID_FILTER` ×5 |
| 5 | `logql.*` | 허용 값 조합별 생성 문자열 스냅샷 | §4.5와 동일 |
| 6 | `logql.audit` | actor `sangplusbot/admin:1.7` | `.`이 `\\.`로 이스케이프 |
| 7 | `FwctlClient` | §6.1 매핑 표의 모든 행 | 코드·details 일치 |
| 8 | 〃 | 헤더에 Bearer·`X-Request-Id`, 본문 `actor` 값 | 요청 캡처로 확인 |
| 9 | 〃 | 토큰 빈 값 | 요청 0회, `FWCTL_AUTH_FAILED` |
| 10 | `GrafanaClient.rules` | 실측 응답 픽스처(룰 8개) | 룰 8개, 라벨 4종, 상태 정규화 |
| 11 | 〃 | 그룹 없음 / `status!="success"` / 비JSON / 401 / 타임아웃 | 전부 `GRAFANA_UNAVAILABLE` |
| 12 | `GrafanaClient.loki_*` | vector·streams 실측 형태 픽스처, 줄 JSON 파싱 실패 1건 섞임 | 정상 건만 반환 + warning |
| 13 | `FirewallObservabilityService.alerts` | 발화 1·대기 1·nodata 7 인스턴스 | 정렬, nodata 5개 제한, `firing_count` |
| 14 | `FirewallControlService.block` | 가짜 포트 | `actor="sangplusbot/admin:<id>"`, 검증 실패 시 포트 호출 0회 |
| 15 | 라우터 | 7개 경로 × (무토큰 401, 일반 사용자 403, admin 2xx) | |
| 16 | 라우터 | `POST /blocks` 본문에 `actor` 포함 | 422 |
| 17 | 라우터 | status: fwctl 불통 | 200, `reachable=false` |
| 18 | 라우터 | 응답 JSON 전체에 토큰 문자열 없음 | 7개 경로 |
| 19 | 조립 | enabled=false | `/api/v1/admin/firewall/status` 404, 다른 라우트 목록 불변 |
| 20 | 조립 | enabled, 토큰 빈 값 | 기동 성공, warning 1회, `configured=false` |
| 21 | 계약(AST) | `src/` 전체에서 `firewall_admin` 패키지를 import하는 파일 | 모듈 자신, `admin_firewall_router.py`, `firewall_admin_di.py`, `interfaces/schemas/firewall_admin.py`뿐 |
| 22 | 실측 | fwctl dry-run: status → block → list → unblock | 전부 성공, `dry_run=true`, 감사 4줄에 같은 접두 actor |
| 23 | 실측 | Grafana: rules, query, query_range (Viewer 토큰) | 파싱 성공 |

### 8.3 L2 프론트 테스트 시나리오

| # | 대상 | Action | 기대 |
|---|---|---|---|
| 1 | 페이지 | status 404 | 꺼짐 안내, 탭 없음 |
| 2 | 상태 띠 | dry_run true / false / reachable false / configured false | DRY-RUN / LIVE / 연결 안 됨 / 설정 필요 |
| 3 | 차단 폼 | 잘못된 IP, TTL 0, 사유 빈 값 | 버튼 비활성 + 메시지 |
| 4 | 차단 폼 | 정상 입력 → 차단 요청 | 확인창에 모드·IP·TTL·사유. 취소 시 요청 0회 |
| 5 | 차단 폼 | 확인 → 201 `dry_run=true` | "실제로 차단되지 않았습니다", blocks 재조회 |
| 6 | 차단 폼 | LIVE 모드 확인창 | 경고 문구 |
| 7 | 차단 폼 | 403 `FORBIDDEN_WHITELIST` / 502 `FWCTL_AUDIT_ERROR` | 코드별 문구 |
| 8 | 차단 폼 | 처리 중 버튼 | `isPending`으로 비활성(요청 1회) — 지연 응답 핸들러로 검증 |
| 9 | 목록 | 2건 응답 | 행 2개, 남은 시간 형식 |
| 10 | 목록 | 해제 → 확인 → 200 / `already_absent` | 재조회 / 안내 문구 |
| 11 | 탐지 탭 | 룰 8개(발화 1) | 발화 룰이 맨 위, 탭 배지 1 |
| 12 | 탐지 탭 | "이 IP 차단" | 현황 탭 전환, IP·사유 초안 채워짐 |
| 13 | 탐지 탭 | `action_hint=report` 인스턴스 | 차단 버튼 없음 |
| 14 | 탐지 탭 | 503 | 안내 문구, 현황 탭은 정상 동작 |
| 15 | 감사 탭 | 필터 변경 | 쿼리 파라미터 반영 |
| 16 | 감사 탭 | actor 접두별 | "관리자"/"에이전트" 표시 |
| 17 | 승인 탭 | 승인 3건(block_ip 1, unblock_ip 1, 다른 도구 1) | 2건만 표시 |
| 18 | 승인 탭 | 승인 클릭 | 기존 approve API 1회 호출 |
| 19 | 승인 탭 | 0건 | 빈 상태 + 연동 안내 |
| 20 | `adminNav` | 그룹 5개, `/admin/firewall`이 `security` 그룹 | 기존 G1·G4 기대값 갱신, G5(진입 경로) 불변 |

MSW 핸들러는 훅이 실제로 읽는 필드와 같은 형태로 만든다(§4.2 예시 JSON을 그대로 픽스처로 쓴다).

### 8.4 L3 E2E Scenario

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|------------------|
| 1 | dry-run 왕복 (SC-3·4) | 로그인 → /admin/firewall → 172.28.10.66 TTL 60 차단 → 안내 확인 → 감사 탭 | "실제로 차단되지 않았습니다", 감사 행 수행자 `sangplusbot/admin:<id>` |
| 2 | 안전장치 (SC-5) | 172.28.10.10 차단 시도 / TTL 99999 | 보호 대상 문구 / 입력 단계에서 막힘 |
| 3 | LIVE 왕복 (SC-6) | fireware `FWCTL_DRY_RUN=false` 재기동 → attacker 차단 | 목록에 남은 시간, 탐지 탭 구분=block 로그, 만료 후 목록에서 사라짐 |
| 4 | 탐지 (SC-7) | attacker 프로파일 가동 5분 | 발화 룰 + `172.28.10.66`, "이 IP 차단" 동작 |
| 5 | 장애 분리 (SC-8) | grafana 컨테이너 중지 / fwctl 중지 | 탭별 안내, 다른 탭 정상 |
| 6 | 꺼짐 (SC-1) | `FIREWALL_ADMIN_ENABLED=false` 재기동 | 메뉴 없음, 직접 진입 시 안내 |
| 7 | 토큰 (SC-9) | `npm run build` 산출물·응답 본문 검색 | 0건 |
| 8 | 승인 (SC-10) | 연동 준비 후 에이전트가 block_ip 요청 | 승인 탭에 표시·처리. 연동 미완료면 이월 |

### 8.5 Seed Data Requirements

| 대상 | 최소 | 준비 방법 |
|---|---|---|
| fireware 랩 | firewall·fwctl·client·server·loki·alloy·grafana Up | worktree에서 `docker compose up -d --build` (firewall과 fwctl을 함께) |
| 차단 로그 | 1건 이상 | `docker compose exec client nc -zv -w 3 172.28.20.10 22` |
| 발화 알림 | 1건 | `docker compose --profile attack up -d attacker` 후 5분 |
| Grafana 서비스 계정 | Viewer 1개 + 토큰 | §11.4 |
| idt 사용자 | admin 1, 일반 1 | 기존 로컬 계정 |
| Grafana 응답 픽스처 | rules 1, vector 1, streams 1 | module-2에서 실측 응답을 저장(`tests/fixtures/firewall_admin/`) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Presentation** | 라우터, 요청·응답 스키마 / 페이지·탭·훅 | `idt/src/api/routes/admin_firewall_router.py`, `idt/src/interfaces/schemas/firewall_admin.py` / `idt_front/src/pages/AdminFirewallPage/`, `src/hooks/` |
| **Application** | 서비스 2개, 포트 | `idt/src/application/firewall_admin/` |
| **Domain** | 모델, 검증, LogQL 템플릿, 오류 | `idt/src/domain/firewall_admin/` |
| **Infrastructure** | fwctl·Grafana HTTP 클라이언트 | `idt/src/infrastructure/firewall_admin/` |
| **조립** | 설정 → 부품 → 라우터 등록 | `idt/src/api/firewall_admin_di.py` |

### 9.2 Dependency Rules

```
router ──► application(services, ports) ──► domain(models, validation, logql, errors)
                     ▲
infrastructure(clients) ──► domain          (포트는 구조적으로 만족, application import 없음)
firewall_admin_di ──► 전부                  (코어에서 이 모듈을 아는 유일한 지점 + main.py 한 줄)
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| `domain/firewall_admin` | 표준 라이브러리 | httpx, fastapi, 다른 도메인 |
| `application/firewall_admin` | `domain/firewall_admin`, 로거 인터페이스 | infrastructure, fastapi |
| `infrastructure/firewall_admin` | `domain/firewall_admin`, httpx | application, fastapi |
| 라우터 | application, domain 오류, schemas, `require_role` | infrastructure |
| 코어(그 밖 `src/`) | 없음 | `firewall_admin` 전체 (테스트 #21로 고정) |

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `models.py`, `errors.py`, `validation.py`, `logql.py` | Domain | `idt/src/domain/firewall_admin/` |
| `ports.py`(`FwctlPort`, `GrafanaPort`), `control_service.py`, `observability_service.py` | Application | `idt/src/application/firewall_admin/` |
| `fwctl_client.py`, `grafana_client.py` | Infrastructure | `idt/src/infrastructure/firewall_admin/` |
| `admin_firewall_router.py` | Presentation | `idt/src/api/routes/` |
| `firewall_admin.py` (Pydantic) | Presentation | `idt/src/interfaces/schemas/` |
| `firewall_admin_di.py` | 조립 | `idt/src/api/` |
| 페이지·탭 6개 | Presentation | `idt_front/src/pages/AdminFirewallPage/` |
| `useFirewall.ts` | Application | `idt_front/src/hooks/` |
| `firewallService.ts` | Infrastructure | `idt_front/src/services/` |
| `firewall.ts` | Domain | `idt_front/src/types/` |

---

## 10. Coding Convention Reference

### 10.1 Naming Conventions

| Target | Rule | Example |
|--------|------|---------|
| 백엔드 패키지 | `firewall_admin` | `src/domain/firewall_admin/` |
| 설정 필드 | `firewall_admin_*` (env는 대문자) | `firewall_admin_fwctl_token` |
| 오류 코드 | UPPER_SNAKE, MCP 서버와 같은 이름 | `FWCTL_AUDIT_ERROR` |
| actor | `sangplusbot/admin:<user_id>` | `sangplusbot/admin:17` |
| 프론트 페이지 | `AdminFirewallPage`, 탭은 `Firewall*Tab` | `FirewallAuditTab.tsx` |
| API 상수 | `ADMIN_FIREWALL_*` | `ADMIN_FIREWALL_BLOCK_DETAIL(ip)` |
| 쿼리 키 | `queryKeys.admin.firewall*()` — `['admin', 'firewall', <자원>, <파라미터>]` | `['admin','firewall','audit',{range,event}]` |
| JSON 필드 | snake_case (백엔드 응답 그대로) | `ttl_remaining_seconds` |

### 10.2 Import Order

기존 규칙(idt: 표준 → 서드파티 → `src.`, idt_front: 외부 → `@/` → 상대 → type)을 따른다.

### 10.3 Environment Variables

| Variable | Default | 소비 지점 |
|---|---|---|
| `FIREWALL_ADMIN_ENABLED` | `false` | `firewall_admin_di.build_firewall_admin()` `if not settings.firewall_admin_enabled` |
| `FIREWALL_ADMIN_FWCTL_URL` | `http://127.0.0.1:8070` | 같은 함수 → `FwctlClient(base_url=)` |
| `FIREWALL_ADMIN_FWCTL_TOKEN` | `""` | 같은 함수 → `FwctlClient(token=)` |
| `FIREWALL_ADMIN_GRAFANA_URL` | `http://127.0.0.1:3000` | 같은 함수 → `GrafanaClient(base_url=)`, status `dashboard_url` |
| `FIREWALL_ADMIN_GRAFANA_TOKEN` | `""` | 같은 함수 → `GrafanaClient(token=)` |

타임아웃(5초·10초), 데이터소스 uid(`loki`), 룰 그룹 이름(`firewall-detection`), 대시보드 경로는 모듈 상수로 둔다. 설정 키로 만들지 않는다.

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 조립 | `source_viewer_di.py` 형태: `build_*`(순수 조립) / `get_*`(앱 수명 1회) / `wire_*(app)`(라우터 등록) |
| 설정 주석 | 각 필드에 "소비:" 한 줄 (dead config 방지) |
| 로그 | `StructuredLogger("firewall_admin")`, 예외는 `exception=e` |
| Design 참조 주석 | 모듈 머리 `Design Ref: firewall-admin-console §N`, 핵심 로직 `Plan SC-N`. 훅·서비스·타입 파일은 `// firewall-admin-console §N — …` 짧은 형식도 허용(같은 추적 정보) |
| 프론트 상수 | 컴포넌트 파일에서 런타임 export 금지 → `src/types/firewall.ts`에 `as const` |
| 뮤테이션 버튼 | `LoadingButton` + `mutateAsync` try/catch |
| 서버 상태 | TanStack Query. 폴링 `refetchInterval`: status 30초(방화벽 페이지만 — 메뉴는 `poll:false`로 갱신하지 않음), blocks 10초, alerts·events·승인 30초, audit 수동(`staleTime: 0`). fwctl health 실패는 debug 로그 |
| status 404 처리 | `retry: false`, 404면 `enabled=false`로 해석 |
| 메뉴 숨김 | `ADMIN_NAV_GROUPS`에는 항상 정의하고, `selectAdminNavGroups`(순수 함수)가 꺼져 있으면 `security` 그룹을 뺀다. 사이드바(`AdminLayout`)와 상단 메뉴(`TopNav`)는 `useAdminNavGroups` 훅으로 이 결과를 쓴다. 관리자가 아니면 status를 묻지 않는다. 경로 → 그룹 역산(`findAdminGroupByPath`)과 2차 탭은 전체 목록 기준이라 직접 진입해도 탭이 보인다 |
| 차단 폼 초안 | 초안은 폼의 초기값으로만 쓰고, 새 초안이 오면 부모가 `key`(nonce)를 바꿔 폼을 새로 만든다(effect로 상태를 덮어쓰지 않는다) |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├─ src/config.py                                        [수정] firewall_admin_* 5개
├─ src/api/main.py                                      [수정] wire_firewall_admin(app) 1줄 + 종료 훅 1줄
├─ src/api/firewall_admin_di.py                         [신규]
├─ src/api/routes/admin_firewall_router.py              [신규]
├─ src/interfaces/schemas/firewall_admin.py             [신규]
├─ src/domain/firewall_admin/{__init__,models,errors,validation,logql}.py          [신규 5]
├─ src/application/firewall_admin/{__init__,ports,control_service,observability_service}.py  [신규 4]
├─ src/infrastructure/firewall_admin/{__init__,fwctl_client,grafana_client}.py     [신규 3]
├─ .env.example                                         [수정] 5개 키 (사용자 확인 후)
└─ tests/
   ├─ domain/firewall_admin/test_validation.py, test_logql.py
   ├─ application/firewall_admin/test_control_service.py, test_observability_service.py
   ├─ infrastructure/firewall_admin/test_fwctl_client.py, test_grafana_client.py
   ├─ api/test_admin_firewall_router.py, test_firewall_admin_wiring.py
   ├─ contracts/test_firewall_admin_isolation.py
   ├─ integration/test_firewall_admin_live.py           (FIREWALL_ADMIN_LIVE=1)
   └─ fixtures/firewall_admin/*.json

idt_front/
├─ src/App.tsx                                          [수정] 라우트 1줄
├─ src/constants/adminNav.ts                            [수정] security 그룹
├─ src/constants/adminNav.test.ts                       [수정] G1·G4 기대값
├─ src/constants/api.ts                                 [수정] ADMIN_FIREWALL_*
├─ src/components/layout/AdminLayout.tsx, TopNav.tsx   [수정] useAdminNavGroups 사용 (AdminSectionTabs 는 무수정 — 경로 역산은 전체 목록)
├─ src/components/layout/AdminNavFirewall.test.tsx      [신규] 메뉴 조건부 노출
├─ src/hooks/useAdminNavGroups.ts                       [신규]
├─ src/lib/queryKeys.ts                                 [수정] admin.firewall*
├─ src/types/firewall.ts                                [신규]
├─ src/services/firewallService.ts                      [신규]
├─ src/hooks/useFirewall.ts (+ useFirewall.test.tsx)    [신규]
├─ src/pages/AdminFirewallPage/
│   ├─ index.tsx
│   ├─ index.test.tsx                  상태 띠·차단 폼·차단 목록
│   ├─ tabs.test.tsx                   탐지·감사·승인 탭·탭 배지
│   ├─ FirewallStatusBar.tsx
│   ├─ FirewallBlocksTab.tsx, BlockIpForm.tsx
│   ├─ FirewallDetectionTab.tsx
│   ├─ FirewallAuditTab.tsx
│   └─ FirewallApprovalsTab.tsx
└─ src/__tests__/mocks/firewallMocks.ts                 [신규]

docs/
├─ 03-analysis/firewall-admin-console.analysis.md       [신규] Check
└─ firewall-admin-setup.md                              [신규] 연동 준비 절차 (§11.4)
```

### 11.2 Implementation Order

**module-1 — 백엔드 fwctl 프록시 (Plan M1)**
1. [x] 선행: fireware 랩 재기동(§11.4-1), `curl 127.0.0.1:8070/healthz` 확인
2. [x] `domain`: models, errors, `validation`(차단 요청) — 테스트 #1~3 먼저
3. [x] `infrastructure/fwctl_client.py` — 테스트 #7~9 먼저(`MockTransport`)
4. [x] `application`: `ports.FwctlPort`, `control_service` — 테스트 #14
5. [x] `config.py` 5개 필드, `firewall_admin_di.py`(fwctl 부분), `main.py` 배선
6. [x] schemas, 라우터 4개 경로(status·blocks 3종) — 테스트 #15~20
7. [x] 격리 계약 테스트 #21
8. [x] 실측 #22 (dry-run 왕복, fwctl 감사에서 actor 확인)
9. [x] 회귀: `FAILED` 목록 diff

**module-2 — 백엔드 Grafana 조회 (Plan M2)**
10. [x] 선행: 서비스 계정 토큰 발급(§11.4-2), Viewer 토큰으로 3개 경로 실측 → 응답을 픽스처로 저장. 거부되면 §4.4 갱신
11. [x] `domain`: `logql`, `validation`(조회 필터) — 테스트 #4~6
12. [x] `infrastructure/grafana_client.py` — 테스트 #10~12
13. [x] `observability_service` — 테스트 #13
14. [x] 라우터 3개 경로(alerts·events·audit), di 확장 — 테스트 #15·#18 확장
15. [x] 실측 #23, 회귀 diff

**module-3 — 프론트 현황·수동 조작 (Plan M3)**
16. [x] `types/firewall.ts`, `constants/api.ts`, `firewallService.ts`, MSW 핸들러
17. [x] 훅(status·blocks·block·unblock) + 테스트
18. [x] `adminNav.ts` security 그룹 + 선택 함수, 소비처 3곳 반영, `adminNav.test.ts` 갱신 — 테스트 #20
19. [x] 페이지 골격·상태 띠·꺼짐 안내 — 테스트 #1·#2
20. [x] `BlockIpForm`, `FirewallBlocksTab` — 테스트 #3~10
21. [x] `App.tsx` 라우트, `tsc -b`, 린트(master와 비교), 브라우저에서 dry-run 왕복 확인

**module-4 — 프론트 탐지·감사·승인 탭 (Plan M4)**
22. [x] 훅(alerts·events·audit) + 테스트
23. [x] `FirewallDetectionTab` + 폼 초안 전달 — 테스트 #11~14
24. [x] `FirewallAuditTab` — 테스트 #15·#16
25. [x] `FirewallApprovalsTab`(기존 승인 훅 재사용, 실제 `tool_id` 형식은 로컬 DB의 MCP 도구 행으로 확인) — 테스트 #17~19
26. [x] 탭 배지, `tsc -b`, 린트, 프론트 회귀(`--no-file-parallelism`)

**module-5 — 연동 준비 절차·검증 (Plan M5)**
27. [x] `docs/firewall-admin-setup.md` 작성(§11.4)
28. [x] L3 시나리오 1~7 실행, 8은 연동 완료 시
29. [ ] `.env.example`·`SOURCE-OF-TRUTH.md` 반영 여부 사용자 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 백엔드 fwctl 프록시 | `module-1` | domain 검증, fwctl 클라이언트, 제어 서비스, 조립, 라우터 4경로, 격리 테스트, dry-run 실측 | 35-45 |
| 백엔드 Grafana 조회 | `module-2` | 토큰 발급·실측, LogQL 템플릿, Grafana 클라이언트, 관측 서비스, 라우터 3경로 | 30-40 |
| 프론트 현황·수동 조작 | `module-3` | 타입·서비스·훅, 메뉴, 상태 띠, 차단 폼·목록 | 35-45 |
| 프론트 탐지·감사·승인 | `module-4` | 탭 3개, 폼 초안 전달, 배지 | 30-40 |
| 연동 준비·검증 | `module-5` | 준비 절차 문서, E2E 시나리오 | 15-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| 1 (완료) | Plan + Design | 전체 | - |
| 2 | Do | `--scope module-1,module-2` | 65-85 |
| 3 | Do | `--scope module-3` | 35-45 |
| 4 | Do | `--scope module-4,module-5` | 45-65 |
| 5 | Check + Report | 전체 | 30-40 |

module-1과 module-2는 같은 세션이 낫다. 조립 파일과 라우터를 이어서 확장한다. 프론트는 module-1·2의 응답 예시(§4.2)가 고정된 뒤 시작한다.

### 11.4 연동 준비 절차 (`docs/firewall-admin-setup.md` 원본)

1. **fireware 랩 기동**
   - 대상: `C:\Users\tkdrb\project\fireware\.claude\worktrees\log-stack-fwctl` (브랜치 `worktree-log-stack-fwctl`). `main` 반영은 fireware 저장소 작업이며 이 사이클의 필수 조건은 아니다
   - `docker compose up -d --build` — firewall과 fwctl을 반드시 함께 올린다(firewall만 재시작하면 fwctl이 고아 netns에 남는다)
   - 확인: `curl -s http://127.0.0.1:8070/healthz` → `"dry_run": true`, `"ipset_exists": true`
2. **Grafana 서비스 계정**
   - Grafana(`http://127.0.0.1:3000`, admin) → Administration → Service accounts → 추가(이름 `sangplusbot-firewall-admin`, 역할 Viewer) → 토큰 생성
   - 토큰은 `idt/.env`의 `FIREWALL_ADMIN_GRAFANA_TOKEN`에만 둔다. mcp-grafana 등록에 같은 계정을 쓸지는 그때 결정한다
3. **idt 설정**
   - `idt/.env`: `FIREWALL_ADMIN_ENABLED=true`, `FIREWALL_ADMIN_FWCTL_TOKEN=<fireware .env의 FWCTL_TOKEN>`, `FIREWALL_ADMIN_GRAFANA_TOKEN=<2번 토큰>`
   - 백엔드 재시작(`--reload`는 설정 변경을 반영하지 않는다). 기동 로그에서 `firewall_admin enabled` 확인
   - idt를 컨테이너로 띄우면 URL 두 개를 `http://host.docker.internal:<port>`로 바꾼다
4. **에이전트 연동 (승인 탭 실건 확인용, 화면 조작)**
   - agent_mcp: `mcp-firewall-server` 기동(호스트 포트 8008, `FIREWALL_FWCTL_TOKEN` 설정)
   - Agent Builder → 관리자 → MCP 서버: `mcp-firewall-server`(SSE, `http://localhost:8008/sse`) 등록 → 연결 테스트 → 도구 동기화
   - 관리자 → 도구 관리: `block_ip`(필요하면 `unblock_ip`)를 승인 필요로 지정
   - 관리자 → 도구 권한: 방화벽 도구를 사용할 사용자·부서만 허용
   - 에이전트 빌더: 방화벽 에이전트 생성, 프롬프트는 fireware `docs/detection-policy.md`를 원본으로 사용, 도구에 `mcp-firewall-server` 4종과 로그 조회 도구(mcp-grafana) 추가
   - 스케줄 등록은 판단 품질을 dry-run으로 확인한 뒤에 한다
5. **LIVE 전환 (선택, SC-6 검증용)**
   - fireware `.env`의 `FWCTL_DRY_RUN=false` → `docker compose up -d firewall fwctl` → 화면 상태 띠가 LIVE로 바뀌는지 확인 → 검증 후 `true`로 되돌린다

### 11.5 핵심 코드 골격

```python
# src/api/firewall_admin_di.py
# Design Ref: firewall-admin-console §6.3, §9.2 — 코어에 끼우는 단일 지점 (source_viewer_di 선례)
@dataclass(frozen=True)
class FirewallAdminParts:
    control: FirewallControlService
    observability: FirewallObservabilityService
    fwctl: FwctlClient
    grafana: GrafanaClient

def build_firewall_admin(settings, logger) -> FirewallAdminParts | None:
    if not settings.firewall_admin_enabled:
        return None
    try: ...  # 클라이언트 2개 → 서비스 2개, 미설정 warning
    except Exception as e:
        logger.warning("firewall_admin assembly failed — feature disabled", exception=e)
        return None

def wire_firewall_admin(app: FastAPI) -> bool:
    parts = get_firewall_admin()
    if parts is None:
        return False
    app.dependency_overrides[admin_firewall_router.get_control_service] = lambda: parts.control
    app.dependency_overrides[admin_firewall_router.get_observability_service] = lambda: parts.observability
    app.include_router(admin_firewall_router.router)
    return True

async def close_firewall_admin() -> None: ...  # 두 클라이언트 aclose
```

```python
# src/api/routes/admin_firewall_router.py
router = APIRouter(
    prefix="/api/v1/admin/firewall", tags=["Admin Firewall"],
    dependencies=[Depends(require_role("admin"))],
)

@router.post("/blocks", status_code=201, response_model=BlockResponse)
async def block_ip(body: BlockRequestBody,
                   current_user: User = Depends(require_role("admin")),
                   service=Depends(get_control_service)):
    request_id = admin_request_id(str(current_user.id))   # adm-<user_id>-<난수>
    try:
        result = await service.block(
            BlockRequest(body.ip, body.ttl_seconds, body.reason),
            user_id=str(current_user.id), request_id=request_id)
    except FirewallAdminError as e:
        raise _http(e, request_id) from e
    return BlockResponse.from_domain(result)
```

```ts
// src/types/firewall.ts
export const FIREWALL_TABS = ['blocks', 'detection', 'audit', 'approvals'] as const;
export const FIREWALL_EVENT_RANGES = ['15m', '1h', '6h', '24h'] as const;
export const FIREWALL_AUDIT_RANGES = ['1h', '6h', '24h', '7d'] as const;
export const FIREWALL_APPROVAL_TOOL_SUFFIXES = ['block_ip', 'unblock_ip'] as const;
```

---

## 12. Plan FR 역추적

| FR | Design 위치 |
|---|---|
| FR-01 off 시 미등록 | §6.3, §11.5, 테스트 #19 |
| FR-02 미설정 warning·`configured=false` | §4.2 status, §6.3, #20 |
| FR-03 admin 전용 | §7, #15 |
| FR-04 status | §4.2 (필드를 `fwctl`·`grafana` 묶음으로 구조화 — Plan의 평면 필드와 같은 정보) |
| FR-05 목록 | §4.2 |
| FR-06 actor 서버 생성 | §4.2·§4.3, #14·#16 |
| FR-07 형식 검증·화이트리스트 위임 | §4.2, §6.1, #1~3 |
| FR-08 dry_run·expires_at·request_id | §4.2 |
| FR-09 해제·already_absent | §4.2, §6.1 |
| FR-10 fwctl 오류 매핑 | §6.1, #7 |
| FR-11 X-Request-Id | §4.3, #8 |
| FR-12 alerts | §4.2·§4.4, #10·#13 |
| FR-13 events | §4.2·§4.5, #5·#12 |
| FR-14 audit | §4.2·§4.5, #4·#6 |
| FR-15 Grafana 장애 분리 | §6.1, L2 #14, L3 #5 |
| FR-16 메뉴 조건부 노출 | §10.4, §5.4 공통, L2 #1·#20 |
| FR-17 모드 배지·불통 표시 | §5.4 공통·현황, L2 #2 |
| FR-18 확인창 | §5.4 현황, L2 #4·#6 |
| FR-19 dry-run 결과 문구 | §5.4 현황, L2 #5 |
| FR-20 10초 폴링·남은 시간 | §10.4, §5.4 현황, L2 #9 |
| FR-21 "이 IP 차단" | §5.4 탐지, L2 #12. 사유 초안은 룰 인스턴스 "{룰 이름} 탐지"(룰 이름에 룰 ID 포함), 출발지 상위는 "차단 로그 {기간} {건수}건" — 인스턴스 `value`가 건수가 아니라 건수는 상위 목록에서만 넣는다(v0.4) |
| FR-22 승인 탭 | §5.4 승인, L2 #17~19 (승인 API 무변경, 프론트 필터로 확정) |
| FR-23 LoadingButton | §10.4, L2 #8 |
| FR-24 토큰 비노출 | §7, #18, L3 #7 |

Plan과 달라진 점: FR-14의 `event` 필터에서 `list`·`health`를 제외했다(폴링으로 대량 발생). 승인 목록 필터는 백엔드 변경 없이 프론트에서 처리한다(Plan 위험 항목의 두 선택지 중 후자).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-23 | Initial draft. Option C 선택. Grafana 12.0.0 API 실측(rules·데이터소스 프록시) 반영. 승인 탭은 프론트 필터, 탐지 탭은 룰 8개 전체 + 발화 강조 | 배상규 |
| 0.2 | 2026-11-23 | module-1·2 구현 반영. 포트 필드 `dest_port`(실측), 대시보드 uid `fireware-firewall-lab`, 요청 ID에 사용자 ID 포함(해제는 fwctl 감사에 actor가 없음), 최근 로그·감사 쿼리는 필터가 없으면 선택자만 사용, 실측 테스트는 환경변수로 실행, Viewer 토큰 실측 완료 | 배상규 |
| 0.3 | 2026-11-23 | module-3 구현 반영. 메뉴 숨김은 `useAdminNavGroups` 훅(소비처는 사이드바·상단 메뉴 2곳), 차단 폼 초안은 key 재생성 방식, 탐지·감사·승인 탭은 자리만 두고 module-4에서 구현, 새 요청을 시작하면 이전 결과 안내를 지움(브라우저 확인에서 발견) | 배상규 |
| 0.4 | 2026-11-24 | module-4 구현 반영. 탐지 탭: 차단 버튼은 발화·대기 인스턴스에만, 인스턴스 `value` 미표시(조건식 결과였음). 감사 탭: 해제 건의 수행자는 요청 ID에서 읽음, 캐시 없이 매번 조회. 승인 탭: `pending` 100건 조회 후 프론트 필터, 기존 거절 사유 창 재사용 | 배상규 |
| 0.5 | 2026-11-24 | module-5 검증 반영. 승인 탭: 응답을 받지 못한 경우(승인 API가 에이전트 재개까지 기다려 30초를 넘김) 실패로 단정하지 않는 안내, 승인·거절 뒤 목록 직접 재조회, 캐시 없이 30초 갱신. Grafana 오류 문구를 탭에 무관한 표현으로 변경. 승인 건의 `tool_id`가 `mcp:<서버>:block_ip` 형식임을 실제 값으로 확인. `block_ip`는 카테고리 미분류로 둬야 함(action이면 워커 제외) — `docs/firewall-admin-setup.md` | 배상규 |
| 0.6 | 2026-11-24 | Check 반영(Match 97.8%). 코드: 형 오류도 같은 코드 형식으로 응답(`INVALID_REQUEST` 추가), 백엔드 `GRAFANA_UNAVAILABLE` 문구 통일, 메뉴용 status 조회는 폴링하지 않음·health 실패 debug 로그, IPv4 정규식 `types/firewall.ts`로 공용화, 감사 수행자 필터를 서버 규칙(영숫자 1자 이상)과 일치. 문서: 표류 D1~D13 정리(함수명·쿼리 키·LogQL 시그니처·파일 구성·기동 로그·토큰 로그·FR-21 초안 형식), 체크리스트 완료 표시 | 배상규 |
