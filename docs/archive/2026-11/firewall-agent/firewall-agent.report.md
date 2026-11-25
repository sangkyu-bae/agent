# firewall-agent 완료 보고서

> **Feature**: firewall-agent (fireware Phase 4 — 보안 에이전트 자동 판단)
> **Period**: 2026-11-24 ~ 2026-11-25
> **Match Rate**: 96% (Act 1회)
> **Status**: 완료 (3개 저장소 미커밋)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|---|---|
| 목표 | 방화벽 탐지 알림을 에이전트가 정책대로 판단해 차단을 요청하고, 운영자는 승인만 한다 |
| 저장소 | sangplusbot(idt·idt_front), agent_mcp(mcp-firewall-server), fireware(정책·프롬프트·Grafana) |
| 설계안 | C(절충) — 코어에는 일반 기능(스케줄 건너뜀·알림 수신)만, 방화벽 전용은 `firewall_admin` 모듈·agent_mcp·fireware |
| 모듈 | M1 조회 도구 · M2 건너뜀 옵션 · M3 알림 수신 · M4 화면 · M5 에이전트 구성 · M6 실측 |

### 1.2 Results Summary

| 항목 | 결과 |
|---|---|
| Success Criteria | 9/10 충족, 1 부분(SC-2 스케줄 회차 성공 실측 이월) |
| Match Rate | 92% → 96% |
| 랩 시나리오 | S1~S6·LIVE 7개 통과 |
| 모델 | Sonnet 4.6 채택(GPT-4o Mini 는 재범 TTL 3/3 위반) |
| 로컬 DB | V098·V099 적용 |

### 1.3 Value Delivered

| 관점 | 내용 |
|---|---|
| **Problem** | 탐지(Grafana 알림)와 집행(fwctl) 사이의 판단을 사람이 로그를 보고 했다. 정책 문서는 있었지만 실행 주체가 없었다 |
| **Solution** | 고정 조회 도구 2개로 근거를 모으고, 정책에서 파생한 지침으로 판단하며, `block_ip` 는 승인 게이트를 거친다. 10분 스케줄과 Grafana 웹훅 두 경로가 같은 바쁨 판정을 거쳐 승인 대기 중에는 건너뛴다 |
| **Function UX Effect** | 랩 실측에서 스캔 IP만 차단 요청(6/6), 보호 주소·정상 트래픽은 요청 0. 승인 대기 중 스케줄 2회·알림 2회가 건너뛰어 같은 IP 요청이 쌓이지 않았다. LIVE 에서 승인 → 실차단 → 재범 알림 → 연장 요청 → 원복까지 사람 손은 승인 두 번이었다. 관리자는 방화벽 화면에서 자동 점검을 켜고 끈다 |
| **Core Value** | "도구를 연결하면 에이전트가 그 도구로 실제 업무를 한다"를 보안 운영에서 확인했다. 건너뜀 옵션·알림 수신은 다른 에이전트도 쓰는 일반 기능으로 남았다 |

## 1.4 Success Criteria Final Status

| SC | 판정 | 근거 |
|---|:-:|---|
| SC-1 조회 도구 | ✅ | agent_mcp 테스트 188건, 실측 .66 묶음 R01·R02·R04·R07 |
| SC-2 S1 스캔(스케줄 회차) | ⚠️ | 요청 내용 6/6 정답. 스케줄 회차 성공 실행은 미실측(직접 실행·알림 잡 경로로 확인, 재기동 시 DLL 차단) |
| SC-3 S2 정상 | ✅ | 6/6 요청 0 |
| SC-4 S3 보호 주소 | ✅ | 6/6 요청 0, "보호 주소 — 무시" 보고 |
| SC-5 S4 승인 대기 | ✅ | 스케줄 02:40·02:50 `skipped(approval_pending)` |
| SC-6 S5 웹훅 | ✅ | 실제 Grafana: disabled 8 · enqueued · resolved_only 3, duplicate 는 재생 |
| SC-7 S6 토글 | ✅ | 자동 점검 API, 화면은 M4 브라우저 확인 |
| SC-8 모델 비교 | ✅ | 2모델 × 3회, 선택 규칙 보강 |
| SC-9 LIVE | ✅ | ipset 등록, fwctl 감사 actor `mcp-firewall-server/prod`, R08 연장 요청·승인(3091→3558초), dry-run 원복 |
| SC-10 회귀 | ✅ | 백엔드 실패 = master 기준선 55건, 옵션 기본 off |

**Overall: 9/10 + 1 부분**

## 1.5 Decision Record Summary

| 결정 | 근거 | 결과 |
|---|---|---|
| 조회는 고정 도구(mcp-grafana 미사용) | LLM 이 LogQL 을 만들면 결과가 흔들린다 | 회차당 도구 2~3회, 판단 근거 일정 |
| 트리거 = 10분 스케줄 + 웹훅, 화면에서 토글 | 놓친 알림 보완 + 빠른 반응 | 두 경로 모두 실측 |
| 승인 대기·실행 중이면 건너뜀(일반 옵션, 기본 off) | 같은 IP 요청 누적 방지 | 4회 건너뜀 실측, 기존 스케줄 영향 없음 |
| 외부 트리거 스크립트 삭제(FR-09) | 백그라운드 워커가 이미 30초마다 실행 | 외부 cron 불필요 |
| 알림 수신은 Alertmanager 형식 일반 기능, Bearer 해시 | HMAC 웹훅은 Grafana 가 못 보냄 | Grafana 12 실제 본문으로 동작 |
| 모델은 시나리오로 비교 | 판단 정확도가 비용보다 우선 | Sonnet 4.6, 규칙에 TTL 정답 조건 추가 |
| LIVE 1회 후 dry-run | 실차단 경로 확인과 안전 | 원복 확인 |

---

## 2. Related Documents

| 단계 | 문서 |
|---|---|
| Plan | [firewall-agent.plan.md](firewall-agent.plan.md) v0.2 |
| Design | [firewall-agent.design.md](firewall-agent.design.md) v0.6 (실측 §8.4.1) |
| Check | [firewall-agent.analysis.md](firewall-agent.analysis.md) v0.2 |
| 준비 절차 | `docs/firewall-admin-setup.md` §5-1 |
| fireware | `docs/detection-policy.md` v0.2, `docs/security-agent-prompt.md`, `docs/runbook.md` |

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 |
|---|---|:-:|
| FR-01~05 | `list_detections`·`get_ip_context`(읽기 전용, 보호 주소 분리, live 이력만, `GRAFANA_UNAVAILABLE`) | ✅ |
| FR-06·07 | 건너뜀 옵션·`skipped` 이력·사유 | ✅ |
| FR-08 | 대기 승인 존재 조회 | ✅ (읽기 전용 포트 `AgentActivityReaderInterface` 로 대체, 설계 v0.2) |
| FR-09 | 트리거 스크립트 | 삭제(설계 v0.1) |
| FR-10~14 | 알림 수신 설정·Bearer·202·firing 만·중복·이력 | ✅ |
| FR-15~17 | 방화벽 자동 점검 API·토글·미설정 안내 | ✅ |
| FR-18~21 | 프롬프트 파일·도구 4종·재현 절차·정책 v0.2·웹훅 활성화 | ✅ |
| FR-22 | IP 마다 한 줄 보고 | ⚠️ 판단은 맞으나 Sonnet 보고가 표로 길다 |

### 3.2 Non-Functional

| 항목 | 결과 |
|---|---|
| 보안 | 토큰 sha256 저장·`compare_digest`, 401 이 존재 여부 비노출, 알림 문구 지시 무시 테두리, `unblock_ip` 미부여, 승인 게이트 |
| 내결함성 | 바쁨 판정 fail-closed, 건너뜀 기록 실패가 틱을 멈추지 않음(G10) |
| 격리 | 코어가 `firewall_admin` 을 import 하지 않음(계약 테스트 I4) |

### 3.3 Deliverables

| 구분 | 내용 |
|---|---|
| idt | `agent_automation`·`agent_alert` 영역, 스케줄 건너뜀, 자동 점검 API, V098·V099, 테스트 |
| idt_front | 스케줄 폼·패널 건너뜀, 빌더 알림 수신 설정, 방화벽 자동 점검 띠 |
| agent_mcp | 조회 도구 2종(테스트 188건) — `mcp-firewall-server` 는 agent_mcp git 미추적 |
| fireware | 정책 v0.2, 에이전트 프롬프트(2,525자), 웹훅 활성화, runbook |
| 로컬 구성 | 보안 에이전트(Sonnet, 스케줄·수신 꺼짐), 비교용 4o-mini 에이전트 |

## 4. Incomplete Items

### 4.1 Carried Over

| 항목 | 이유 | 우선순위 |
|---|---|---|
| SC-2 스케줄 회차 성공 실측 | Smart App Control 이 `_kiwipiepy` DLL 을 연속 차단해 백엔드 기동 불가 | 높음(기동되면 10분) |
| 빈 회차 토큰 비용(LLM 6회·20~33k) | 플랫폼 실행 구조 | 높음(운영 전) |
| 보고 형식(FR-22) | 프롬프트 다듬기 | 중간 |
| G4 수신 이력 작업 링크, G9 본문 크기 선검사, G11 토글 순서 | Minor | 낮음 |

### 4.2 Cancelled

- FR-09 외부 트리거 스크립트(워커가 대신함)

## 5. Quality Metrics

### 5.1 Final Analysis

| 축 | 점수 |
|---|:-:|
| Structural | 98% |
| Functional | 96% |
| Contract | 97% |
| Runtime | 95% |
| **Overall** | **96%** |

### 5.2 Resolved Issues

| 이슈 | 조치 |
|---|---|
| 스케줄 라우터 int user_id → 본인 스케줄도 403 (master 기존 결함) | `str()` 전달 + 회귀 테스트(M4) |
| 새 에이전트 저장 시 대기 스케줄 `skip_when_busy` 누락(G1) | POST 본문 추가 + 회귀 테스트 |
| 건너뜀 기록 실패가 같은 틱 다른 스케줄 중단(G10) | 로그 후 계속 + 회귀 테스트 |
| 중복 import(G12), 설계 표류 6건 | 정리, 설계 v0.6 |

## 6. Lessons Learned

### 6.1 Keep

- 실제 Grafana 12 본문을 연락처 테스트 API 로 먼저 받아 픽스처로 쓴 덕에 수신 형식 문제가 실측에서 나오지 않았다.
- 시나리오마다 승인 요청을 자동 거절하는 측정 스크립트로 모델 비교를 회차 간 간섭 없이 반복했다.

### 6.2 Problem

- 설계의 모델 선택 규칙이 안전 시나리오만 봐서, 문자 그대로 적용하면 정책 TTL 을 어기는 모델이 뽑힐 뻔했다.
- 실측 순서상 스케줄 회차가 승인 대기로 계속 건너뛰어, 스케줄 경로의 "성공"을 따로 확인할 시간을 잡지 못했다.
- 이 PC 의 Smart App Control 이 네이티브 DLL 을 간헐·연속으로 막아 서버 기동이 불안정했다.

### 6.3 Try

- 선택 규칙에 "정책 수치 정답"을 처음부터 넣는다.
- 실측 계획에 "각 트리거 경로의 성공 1회"를 건너뜀 시나리오보다 먼저 둔다.

## 7. Process Improvement

- 서브에이전트(gap-detector)는 Write 도구가 없어 파일 출력 지시를 못 따른다 — 결과를 메시지로 받도록 지시한다.
- 백그라운드 bash 를 멈춰도 자식 uvicorn 은 남는다 — 포트 소유 프로세스를 직접 종료한다.

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋 범위 결정(sangplusbot 브랜치, agent_mcp `mcp-firewall-server` 미추적 디렉터리, fireware 원격 없는 worktree) → PR
- [ ] 서버가 뜨는 때 SC-2 스케줄 1회 확인
- [ ] `/pdca archive firewall-agent`, SOT 갱신

### 8.2 Next Cycle 후보

| 항목 | 이유 |
|---|---|
| 빈 회차 비용 줄이기 | 탐지 없을 때 LLM 6회 — 조회 결과가 비면 짧게 끝나는 실행 경로 |
| 보고 형식 고정 | 운영자가 한눈에 읽게 |

## 9. Changelog

### v1.0.0 (2026-11-25)

- **Added**: 스케줄 "바쁘면 건너뜀" 옵션, 에이전트 알림 수신(Alertmanager 웹훅), 방화벽 자동 점검 API·화면, mcp-firewall-server 조회 도구 2종, fireware 정책 v0.2·보안 에이전트 프롬프트
- **Fixed**: 스케줄 라우터 int user_id 403, 새 에이전트 대기 스케줄 `skip_when_busy` 누락, 건너뜀 기록 실패 시 틱 중단

## Version History

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.0 | 2026-11-25 | 완료 보고 |
