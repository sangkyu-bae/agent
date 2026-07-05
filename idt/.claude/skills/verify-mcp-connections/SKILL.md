---
name: verify-mcp-connections
description: 로컬 DB(MySQL)에 등록된 MCP 서버를 열거하고, 프로덕션과 동일한 코드 경로로 실제 연결(list_tools)을 테스트합니다. "등록된 MCP 붙나 확인", "MCP 연결 테스트", "MCP 진단", "로컬 DB MCP 확인" 요청 시 사용.
---

# MCP 서버 연결 진단 (verify-mcp-connections)

## 목적

로컬 MySQL에 등록된 MCP 서버가 **실제 우리 코드 경로로 연결되는지** 진단합니다.
uvicorn 서버를 띄우지 않고, 프로덕션 런타임과 동일한 코드를 재사용합니다:

```
MCPServerRepository.find_all_active()   # 로컬 DB에서 등록 목록 + 시크릿 복호화
  → MCPConnectionTestUseCase.execute()  # 서버별 연결 테스트
    → MCPToolLoader._build_config()     # transport별 config 조립 (SSE / streamable_http)
    → MCPCallClient.list_tools()        # 실제 MCP 세션 열고 도구 목록 조회
```

에이전트 런타임은 `is_active=True` 서버만 로드하므로, 기본은 **활성 서버만** 테스트합니다.

## 실행 시점

- MCP 서버를 새로 등록/수정한 후 "실제로 붙나?" 확인할 때
- 에이전트가 MCP 도구를 못 쓸 때 원인이 등록/연결에 있는지 切り分け(切り分け=격리 진단)
- 배포 전, 등록된 외부 MCP 엔드포인트가 여전히 살아있는지 헬스체크
- `Session terminated` / 도구 목록 비어있음 등의 증상 조사

## 관련 파일

| File | Purpose |
|------|---------|
| `scripts/verify_mcp_connections.py` | 진단 스크립트 (읽기 전용, 이 스킬의 실행 진입점) |
| `src/application/mcp_registry/mcp_connection_test_use_case.py` | 실제 연결 테스트 UseCase (친화적 에러 매핑 포함) |
| `src/infrastructure/mcp_registry/mcp_server_repository.py` | DB 조회 + 시크릿 복호화 |
| `src/infrastructure/mcp_registry/mcp_tool_loader.py` | transport별 config 조립 |
| `src/infrastructure/mcp/call_client.py` | MCP 세션 연결 / list_tools |

## Workflow

### Step 1: 진단 스크립트 실행

프로젝트 루트(`idt/`)에서:

```bash
# 활성 MCP 서버 전체 테스트 (기본)
python -m scripts.verify_mcp_connections

# 특정 사용자 범위 (비활성 포함)
python -m scripts.verify_mcp_connections --user <user_id>

# JSON 출력 (CI/파이프라인 연동)
python -m scripts.verify_mcp_connections --json
```

- **읽기 전용**입니다. DB를 변경하지 않습니다.
- 실패가 1건이라도 있으면 exit code `1` (전부 성공 시 `0`).

### Step 2: 결과 해석

출력 표의 각 행:

| 컬럼 | 의미 |
|------|------|
| 상태 | `OK` = 세션 연결 + list_tools 성공 / `FAIL` = 연결 또는 조회 실패 |
| 도구 | 조회된 MCP 도구 수 (0이면 연결은 됐으나 도구 미노출 의심) |
| ms | 연결~조회 소요 시간 |
| 비고 | 실패 시 원인 힌트 |

### Step 3: 실패 원인 진단

| 증상(비고) | 원인 | 조치 |
|-----------|------|------|
| `Session terminated` / 404 힌트 | 엔드포인트가 HTTP 404 반환. 주로 **빈 api_key가 Smithery URL에서 누락**되거나 URL 경로(`/mcp`) 오타 | 등록 정보의 `auth_config.api_key`, `endpoint` 확인 후 재등록/수정 |
| 타임아웃 / connection refused | 엔드포인트 미기동 또는 방화벽 | 외부 MCP 서버 상태·네트워크 확인 |
| 도구 0개인데 OK | 연결은 되나 서버가 도구를 노출하지 않음 | MCP 서버 측 설정/권한 확인 |
| `등록된 MCP 서버가 없습니다` | 활성 서버 0건 | 등록 여부 / `is_active` 플래그 확인 |

> 참고: `Session terminated`는 세션 만료가 아니라 **HTTP 404**를 의미합니다.
> (자세한 매핑은 `mcp_connection_test_use_case.py`의 `_friendly_error` 참조)

## Output Format

```markdown
### verify-mcp-connections 결과

- 테스트 대상: N개 (활성)
- 성공: X / 실패: Y

#### 실패 항목
| 이름 | transport | 원인 | 조치 |
|------|-----------|------|------|
| Naver Search | streamable_http | 404 (api_key 누락 의심) | 등록 auth_config 확인 |
```

## 주의사항

- 이 스킬은 **진단(읽기 전용)** 전용입니다. 등록 정보 수정은 `POST /mcp-servers` / `PUT /mcp-servers/{id}` 를 사용하세요.
- 외부 MCP 엔드포인트로 실제 네트워크 요청을 보냅니다. 대량/반복 실행은 대상 서버에 부하가 될 수 있습니다.
- DB 연결이 필요합니다(`.env`의 MySQL 설정). 시크릿 복호화에는 `MCP_SECRET_KEY`(settings.mcp_secret_key)가 있어야 암호화된 auth/server config를 읽습니다.
