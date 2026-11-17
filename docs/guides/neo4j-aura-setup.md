# Neo4j 연결 가이드 (그래프 RAG)

> 대상 독자: 개발자, 시스템 관리자
> 관련 문서: `docs/01-plan/features/graph-rag-foundation.plan.md`, `docs/02-design/features/graph-rag-foundation.design.md`
> 작성일: 2026-11-17

그래프 RAG는 문서에서 추출한 엔티티와 관계를 Neo4j에 저장한다. 이 문서는 Neo4j를 준비하고 백엔드(`idt/`)에 연결하는 절차를 설명한다.

---

## 1. 어떤 Neo4j를 사용하는가

| 단계 | 사용하는 Neo4j | 이유 |
|------|---------------|------|
| 개발·PoC | **Neo4j Aura Free** (Neo4j사가 운영하는 클라우드 서비스) | 서버에 Neo4j를 설치하지 않아도 되고, 12GB 서버의 메모리를 사용하지 않는다. |
| 사내 도입 | **자체 호스팅** 또는 사내 승인 클라우드 | Aura는 외부 클라우드이므로 사내 규정 내용을 계속 보관하기 전에 보안 검토가 필요하다. |

두 방식은 같은 드라이버를 사용한다. 접속 주소(`NEO4J_URI`)만 바꾸면 전환되며 코드는 수정하지 않는다.

- Aura: `neo4j+s://<인스턴스ID>.databases.neo4j.io`
- 자체 호스팅: `bolt://<호스트>:7687`

---

## 2. Aura Free 인스턴스 생성

1. https://console.neo4j.io 에 접속해 Google 계정 또는 이메일로 가입한다. 카드 등록은 필요하지 않다.
2. 콘솔에서 **Create instance**(또는 **New Instance**)를 선택하고 **AuraDB Free**를 고른다.
   - 인스턴스 이름은 자유롭게 정한다. 예: `sangplusbot-graph-poc`
   - 리전을 고를 수 있으면 서울 또는 가까운 아시아 리전을 선택한다. 리전이 고정되어 있으면 그대로 진행한다.
3. 생성 직후 화면에 비밀번호가 **한 번만** 표시된다. **Download** 버튼으로 접속 정보 파일(`.txt`)을 내려받아 보관한다.
   - 파일에는 `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`가 기록되어 있다.
   - 최근에 만든 인스턴스는 사용자명이 `neo4j`가 아니라 인스턴스 ID인 경우가 있다. 파일에 적힌 값을 그대로 사용한다.
4. 상태가 **Running**으로 바뀔 때까지 1~3분 기다린다.

---

## 3. 백엔드 환경변수 설정

`idt/.env`에 다음 항목을 추가한다. worktree에서 작업 중이면 해당 worktree의 `idt/.env`에 추가한다.

```env
GRAPH_BACKEND=neo4j
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=<접속 정보 파일의 NEO4J_USERNAME>
NEO4J_PASSWORD=<접속 정보 파일의 NEO4J_PASSWORD>
NEO4J_DATABASE=neo4j
```

- `.env`는 git에 포함되지 않는다. 비밀번호를 채팅, 이슈, 커밋 메시지에 기록하지 않는다.
- 접속 정보 파일에 데이터베이스 이름이 별도로 있으면 `NEO4J_DATABASE`에 그 값을 넣는다.

### 3.1 전체 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GRAPH_BACKEND` | `off` | `off` 또는 `neo4j`. 값이 잘못되었거나 접속 정보가 없으면 경고 로그를 남기고 `off`로 동작한다. |
| `NEO4J_URI` | (없음) | Aura 또는 자체 호스팅 주소 |
| `NEO4J_USER` | `neo4j` | 사용자명 |
| `NEO4J_PASSWORD` | (없음) | 비밀번호. `.env`에만 기록한다. |
| `NEO4J_DATABASE` | `neo4j` | 데이터베이스 이름 |
| `NEO4J_MAX_POOL_SIZE` | `10` | 드라이버 연결 풀 크기 |
| `NEO4J_CONNECT_TIMEOUT_S` | `5` | 연결 시간 제한(초) |
| `GRAPH_ENTITY_EMBEDDING_MODEL` | (비움) | 엔티티 이름 임베딩 모델. 비우면 `OPENAI_EMBEDDING_MODEL`을 사용한다. |
| `GRAPH_ENTITY_EMBEDDING_DIMENSIONS` | `512` | 벡터 인덱스 차원. Aura Free 저장 용량을 줄이기 위해 512로 정했다. |
| `GRAPH_AURA_FREE_NODE_LIMIT` | `200000` | 관리자 화면에 표시할 노드 한도 |
| `GRAPH_AURA_FREE_REL_LIMIT` | `400000` | 관리자 화면에 표시할 관계 한도 |

노출 단계(`off`·`admin_only`·`general`), 추출 사용 여부, Jev 판정 사용 여부 같은 운영 설정은 환경변수가 아니라 DB(`graph_rag_setting`)에 저장한다. 관리자 API 또는 관리자 화면에서 변경한다.

### 3.2 Neo4j 드라이버 설치

드라이버는 선택 의존성 `graph`에 포함되어 있다.

```bash
cd idt
uv sync --extra dev --extra graph
```

드라이버가 설치되지 않은 상태에서 `GRAPH_BACKEND=neo4j`로 실행하면 경고 로그를 남기고 그래프 기능 없이 기동한다.

---

## 4. 연결 확인

### 4.1 실연결 테스트

실제 Neo4j에 연결하는 테스트는 기본 실행에서 제외되어 있다. `-m neo4j`를 지정해야 실행된다.

```bash
cd idt
uv run python -m pytest -m neo4j tests/infrastructure/graph_rag/test_neo4j_store.py
```

이 테스트는 다음을 확인한다.

- 연결(`verify_connectivity`)이 성공한다.
- 제약 조건, 인덱스, 512차원 벡터 인덱스가 생성되고, 두 번 실행해도 오류가 없다.
- 노드 수와 관계 수를 조회할 수 있다.

### 4.2 관리자 API

백엔드를 실행한 뒤 관리자 계정 토큰으로 상태를 조회한다.

```bash
curl -H "Authorization: Bearer <관리자 토큰>" \
  http://localhost:8000/api/v1/admin/graph-rag/health
```

정상 응답 예시:

```json
{
  "backend": "neo4j",
  "connected": true,
  "external": true,
  "node_count": 0,
  "relationship_count": 0,
  "node_limit": 200000,
  "relationship_limit": 400000,
  "error": null
}
```

`external: true`는 데이터가 Aura(외부 클라우드)에 저장된다는 뜻이다.

### 4.3 기동 시 동작

백엔드는 기동할 때 Neo4j에 제약 조건과 인덱스를 생성한다. 이미 있으면 건너뛴다.

| 상황 | 동작 |
|------|------|
| 연결 성공 | 스키마를 생성하고 그래프 기능을 사용한다. |
| 연결 실패(Aura 일시 정지 등) | 경고 로그만 남기고 기동한다. 연결이 회복되면 다시 사용한다. |
| 기존 벡터 인덱스 차원과 설정 차원이 다름 | 오류 로그를 남기고 그래프 기능을 끈다. §6.2를 참고한다. |

어느 경우에도 업로드와 채팅은 그래프 없이 정상 동작한다.

---

## 5. Aura Free 운영 시 주의사항

| 항목 | 내용 | 대응 |
|------|------|------|
| 용량 한도 | 노드 20만 개, 관계 40만 개 (2026-11 기준, 가입 시 가격 페이지에서 다시 확인) | 관리자 화면의 노드·관계 수로 사용량을 확인한다. |
| 자동 일시 정지 | 쓰기 작업 없이 3일이 지나면 정지된다. 조회만으로는 활동으로 인정되지 않을 수 있다. | 콘솔에서 **Resume**을 선택한다. |
| 자동 삭제 | 정지 상태로 30일이 지나면 삭제된다. | 그래프는 문서를 다시 추출해 복구할 수 있다. 판정 기록과 추출 이력은 MySQL에 남는다. |
| 백업 | 제공되지 않는다. | 위와 같이 재추출로 복구한다. |
| 데이터 범위 | 외부 클라우드에 저장된다. | PoC에는 고객 개인정보가 없는 규정 문서만 사용한다. |
| 지연 시간 | 검색할 때마다 외부 왕복이 발생한다. | 서버와 가까운 리전을 선택한다. 그래프 검색이 설정한 시간 제한(기본 800ms)을 넘으면 그래프 결과를 사용하지 않고 기존 검색 결과로 응답한다. |

---

## 6. 문제 해결

### 6.1 증상별 원인

| 증상 | 확인할 것 |
|------|----------|
| health의 `backend`가 `off` | `GRAPH_BACKEND=neo4j`, `NEO4J_URI`, `NEO4J_PASSWORD`가 모두 설정되었는지, 드라이버가 설치되었는지(§3.2) 기동 로그의 경고 메시지로 확인한다. |
| `connected: false`, 오류에 `ServiceUnavailable` | 콘솔에서 인스턴스 상태를 확인한다. **Paused**이면 **Resume**을 선택한다. |
| 오류에 `AuthError` | 사용자명이 접속 정보 파일의 `NEO4J_USERNAME`과 같은지 확인한다. 비밀번호를 잊었으면 콘솔에서 재설정한다. |
| 주소 해석 오류 | `NEO4J_URI`가 `neo4j+s://`로 시작하는지, 인스턴스 ID가 정확한지 확인한다. |

### 6.2 벡터 인덱스 차원 불일치

기동 로그에 `graph store disabled — embedding dim mismatch`가 기록되면, Neo4j에 이미 있는 벡터 인덱스의 차원과 `GRAPH_ENTITY_EMBEDDING_DIMENSIONS`가 다른 것이다.

- 설정을 기존 인덱스 차원에 맞추거나,
- Neo4j에서 기존 인덱스(`entity_name_vec`)를 삭제한 뒤 재기동하고 문서를 다시 추출한다.

차원을 바꾸면 기존 엔티티 임베딩을 다시 계산해야 한다.

---

## 7. 자체 호스팅으로 전환

사내 도입 단계에서 Aura를 자체 호스팅으로 바꾸는 절차다.

1. 사내 보안 검토를 먼저 받는다.
2. Neo4j 5를 설치한다. Docker를 사용하는 예시는 다음과 같다.

   ```bash
   docker run -d --name neo4j \
     -p 7687:7687 \
     -e NEO4J_AUTH=neo4j/<비밀번호> \
     -e NEO4J_server_memory_heap_max__size=512m \
     -e NEO4J_server_memory_pagecache_size=512m \
     -v neo4j-data:/data \
     neo4j:5
   ```

   메모리 설정은 12GB 서버(small 프로필) 기준으로 heap과 pagecache 합계 1GB 수준이다. 실제 데이터량에 맞춰 조정한다.
3. `idt/.env`의 `NEO4J_URI`를 `bolt://<호스트>:7687`로 바꾸고, `NEO4J_USER`·`NEO4J_PASSWORD`를 새 값으로 바꾼다.
4. 백엔드를 재기동한다. 스키마는 기동할 때 자동으로 생성된다.
5. 관리자 화면에서 문서 추출을 다시 실행해 그래프를 새로 만든다.

> 확인 필요: 사용할 Neo4j 버전과 에디션에서 벡터 인덱스(`CREATE VECTOR INDEX`)가 지원되는지 설치 후 §4.1 테스트로 확인한다.

---

## 8. 보안 수칙

- 비밀번호는 `idt/.env`에만 기록한다. `.env.example`에는 빈 값만 둔다.
- 로그에 접속 주소의 인증 정보를 남기지 않는다.
- Aura에는 고객 개인정보가 포함된 문서를 적재하지 않는다.
- 그래프 검색 결과는 사용자 권한(공개 범위·부서)으로 청크 단위 필터링을 거치도록 설계했다. 권한이 없는 KB의 청크는 검색 결과에 포함되지 않는다. (그래프 검색은 구현 module-5에서 추가된다. 2026-11-17 기준 미구현)
