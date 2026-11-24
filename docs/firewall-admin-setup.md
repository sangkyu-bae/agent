# 방화벽 관리 화면 준비 절차

> Agent Builder 관리자 메뉴의 **보안 운영 > 방화벽**(`/admin/firewall`)을 쓰기 위한 준비 절차다.
> 대상은 fireware 방화벽 랩(Docker)이며 기본은 dry-run이다.
> 설계: `docs/archive/2026-11/firewall-admin-console/firewall-admin-console.design.md` · 절차는 2026-11-23~24에 로컬에서 실제로 수행해 확인했다.

## 구성

```
브라우저(관리자) ── idt 백엔드 /api/v1/admin/firewall/* ─┬─ fwctl :8070 ── ipset (firewall 컨테이너)
                                                          └─ Grafana :3000 ── 알림 룰 / Loki
에이전트 ── mcp-firewall-server :8008 ── fwctl :8070        (승인 탭에 요청이 올라오는 경로)
```

- 브라우저는 idt API만 호출한다. fwctl·Grafana 토큰은 `idt/.env`에만 둔다.
- dry-run ↔ LIVE 전환은 화면에 없다. fireware `.env`로만 바꾼다.

## 1. fireware 랩 기동

위치: `C:\Users\tkdrb\project\fireware\.claude\worktrees\log-stack-fwctl` (브랜치 `worktree-log-stack-fwctl`)

```sh
docker compose up -d
curl -s http://127.0.0.1:8070/healthz     # "dry_run": true, "ipset_exists": true
```

- **firewall과 fwctl은 함께 올린다.** firewall만 재시작하면 fwctl이 예전 네트워크에 남아 `ipset_exists: false`가 된다. 다시 올릴 때는 `docker compose up -d --force-recreate firewall fwctl`.
- Loki 보존 기간은 7일이다. 랩이 그보다 오래 내려가 있었으면 탐지·감사 탭이 비어 있다.

## 2. Grafana 서비스 계정

1. Grafana(`http://127.0.0.1:3000`, admin) → Administration → Service accounts → 추가
2. 이름 `sangplusbot-firewall-admin`, 역할 **Viewer**
3. 토큰을 만들어 3번의 `FIREWALL_ADMIN_GRAFANA_TOKEN`에 넣는다

Viewer 권한으로 아래 3개 경로가 모두 조회된다(실측).

| 용도 | 경로 |
|---|---|
| 알림 룰 상태 | `/api/prometheus/grafana/api/v1/rules` |
| Loki 순간 쿼리 | `/api/datasources/proxy/uid/loki/loki/api/v1/query` |
| Loki 범위 쿼리 | `/api/datasources/proxy/uid/loki/loki/api/v1/query_range` |

## 3. idt 설정

`idt/.env`에 추가한다(예시는 `idt/.env.example`).

```
FIREWALL_ADMIN_ENABLED=true
FIREWALL_ADMIN_FWCTL_URL=http://127.0.0.1:8070
FIREWALL_ADMIN_FWCTL_TOKEN=<fireware .env 의 FWCTL_TOKEN>
FIREWALL_ADMIN_GRAFANA_URL=http://127.0.0.1:3000
FIREWALL_ADMIN_GRAFANA_TOKEN=<2번에서 만든 토큰>
```

- 백엔드를 **다시 시작**한다(`--reload`는 설정 변경을 반영하지 않는다). 기동 로그에 `firewall_admin enabled`가 남는다.
- 켰는데 URL·토큰이 비어 있으면 기동 로그에 warning이 남고 화면 상태 띠에 "설정 필요"가 보인다.
- idt를 컨테이너로 띄우면 두 URL을 `http://host.docker.internal:<포트>`로 바꾼다.
- `FIREWALL_ADMIN_ENABLED=false`(기본)면 라우터와 메뉴가 없다. 직접 주소로 들어가면 "방화벽 관리 기능이 꺼져 있습니다"가 나온다.

## 4. 화면에서 확인

관리자로 로그인 → 관리 → 보안 운영 → 방화벽.

| 확인 | 기대 |
|---|---|
| 상태 띠 | fwctl 연결됨, 모드 DRY-RUN, TTL 상한 3600초 |
| 현황 탭에서 `172.28.10.66` 차단 | 확인창 → "실제로 차단되지 않았습니다(DRY-RUN)" |
| `172.28.10.10` 차단 | "보호 대상 주소라 차단할 수 없습니다" |
| 감사 탭 | 방금 요청이 "관리자 ID <내 ID>"로 보인다 |
| 탐지 탭 | 룰 8개. 발화를 보려면 `docker compose --profile attack up -d attacker` 후 2~5분 (끝나면 `stop attacker`) |

수행자는 fwctl 감사의 `actor=sangplusbot/admin:<user_id>`로 남는다. 해제는 fwctl 계약상 actor가 없어서 요청 ID(`adm-<user_id>-…`)로 찾는다.

## 5. 에이전트 연동 (승인 탭)

에이전트가 요청한 차단이 승인 탭에 올라오게 하는 절차다.

1. **MCP 서버 기동** — `agent_mcp`에서 토큰을 셸 환경변수로 넣어 올린다(파일에 평문으로 두지 않는다).
   ```sh
   FIREWALL_FWCTL_TOKEN=<FWCTL_TOKEN> docker compose up -d --build mcp-firewall-server
   curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8008/metrics    # 200
   ```
2. **MCP 서버 등록** — 관리 → 에이전트 리소스 → MCP 서버. 이름 `Firewall MCP`, 주소 `http://localhost:8008/sse`, 방식 `sse`. 연결 테스트 후 도구 동기화. 도구 4종(`block_ip`·`unblock_ip`·`list_blocks`·`firewall_health`)이 카탈로그에 생긴다.
3. **승인 필요 지정** — 관리 → 도구 관리에서 `block_ip`(필요하면 `unblock_ip`)의 **승인 필요만 켠다.**
   - **카테고리는 미분류로 둔다.** `action`으로 지정하면 이 도구에는 본문(초안) 인자가 없어서 워커가 실행에서 제외되고, 에이전트가 `block_ip`를 호출하지 못한다(실측).
4. **도구 권한** — 관리 → 조직 관리 → 도구 권한에서 방화벽 도구를 쓸 사용자·부서만 허용한다.
5. **에이전트 구성** — 에이전트 빌더에서 방화벽 에이전트를 만들고 도구 4종을 연결한다. 승인 게이트를 켠다. 프롬프트는 fireware `docs/detection-policy.md`를 원본으로 쓴다. 로그 조회가 필요하면 mcp-grafana를 별도로 등록한다.
6. **확인** — 에이전트에 "172.28.10.66을 60초 차단해 줘"를 보내면 "담당자 승인함에 올렸습니다"로 끝나고, 방화벽 화면의 승인 탭에 요청이 보인다. 승인하면 `block_ip`가 실행되고 감사 탭에 "에이전트" 수행자로 남는다.

알아 둘 점:

- 승인 탭은 **내가 소유한 에이전트의 요청**만 보여 준다. 다른 사람이 소유한 방화벽 에이전트의 요청은 그 사람의 화면에만 나온다.
- 승인 API는 에이전트 재개까지 기다려서 응답이 30초를 넘길 수 있다. 그때 화면은 "응답을 받지 못했습니다. 요청은 처리됐을 수 있습니다"를 보여 주고 목록을 다시 불러온다. 결과는 목록과 감사 탭으로 확인한다.
- 스케줄 등록은 dry-run으로 판단 품질을 확인한 뒤에 한다.

## 6. LIVE 전환

실제로 차단하려면 fireware `.env`를 바꾸고 두 컨테이너를 함께 다시 만든다.

```sh
# fireware worktree 에서
# .env: FWCTL_DRY_RUN=false
docker compose up -d --force-recreate firewall fwctl
curl -s http://127.0.0.1:8070/healthz      # "dry_run": false
```

- 화면 상태 띠가 30초 안에 **LIVE**로 바뀌고, 차단 확인창에 "실제 트래픽이 차단됩니다" 경고가 나온다.
- 차단하면 목록에 남은 시간이 표시되고 유지 시간이 지나면 자동으로 사라진다. 목록의 "해제"로 즉시 풀 수 있다.
- 되돌릴 때는 `FWCTL_DRY_RUN=true`로 바꾸고 같은 명령으로 다시 만든다. 다시 만들면 차단 목록은 비워진다.
- 보호 주소(랩의 firewall·client·server·게이트웨이·루프백)와 TTL 상한(3600초)은 LIVE에서도 fwctl이 거부한다.

## 7. 실장비에 연결하려면

이 화면과 백엔드는 fwctl 계약만 바라본다. 아래가 채워지면 수정 없이 실장비에 붙는다. 이번 범위에는 없다.

| 조건 | 현재 | 필요한 것 |
|---|---|---|
| 집행부 | 컨테이너의 ipset | 실 Linux 게이트웨이(nftables) 또는 상용 방화벽의 외부 차단 목록·API |
| 전송·인증 | 평문 HTTP, 공유 토큰 1개, 루프백 | TLS(mTLS), 호출자별 토큰 |
| 차단 단위 | IPv4 단일 주소 | IPv6·대역, NAT·공유 IP 오차단 대책 |
| 보호 주소 | 환경변수 고정 | 업무망·협력사 대역 관리 절차 |
| 가용성 | 재기동 시 목록 소실, 단일 인스턴스 | 영속화·이중화 |
| 감사 | 파일 무기한, 화면 조회 7일 | 장기 보관·위변조 방지 |
| 조직 | 없음 | 변경관리·정보보호 부서 승인, 로그의 외부 LLM 전송 검토 |

## 8. 문제가 생겼을 때

| 증상 | 원인 | 조치 |
|---|---|---|
| 메뉴에 "보안 운영"이 없다 | 모듈이 꺼져 있거나 백엔드를 재시작하지 않았다 | `FIREWALL_ADMIN_ENABLED=true` 후 재시작 |
| 상태 띠 "연결 안 됨" | fwctl이 내려가 있다 | 1번 절차로 랩 기동 |
| 상태 띠 "ipset 없음" | firewall만 재시작했다 | `up -d --force-recreate firewall fwctl` |
| 차단 시 "fwctl 인증에 실패했습니다" | 토큰이 fireware `.env`와 다르다 | `FIREWALL_ADMIN_FWCTL_TOKEN` 확인 |
| 탐지·감사 탭 "Grafana에서 정보를 가져올 수 없습니다" | Grafana가 내려갔거나 토큰이 틀렸다 | Grafana 기동, 서비스 계정 토큰 확인. 현황 탭은 영향받지 않는다 |
| 탐지·감사 탭이 비어 있다 | 랩이 7일 넘게 내려가 있었다 | 트래픽을 만들어 확인(`client`에서 `nc -zv -w 3 172.28.20.10 22`) |
| 에이전트가 `block_ip`를 호출하지 못한다 | 도구 카테고리가 `action`이다 | 미분류로 바꾼다(5-3) |
| 승인 탭에 요청이 안 보인다 | 다른 사람이 소유한 에이전트다 | 소유자 계정으로 확인하거나 작업함에서 본다 |
