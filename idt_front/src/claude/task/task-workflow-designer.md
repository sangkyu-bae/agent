# WORKFLOW-001 — 워크플로우 설계 페이지

## 상태: 완료 (Mock 데이터 + 비주얼 플로우 에디터)

## 목표
AI 에이전트의 처리 단계(워크플로우)를 시각적으로 탐색·활성화하고,
노드를 선으로 연결하여 에이전트 워크플로우를 직접 설계하는 페이지.

---

## 구현 완료 항목

### 타입
- [x] `src/types/workflow.ts`
  - `Workflow`, `WorkflowStep`, `WorkflowCategory`, `WorkflowStepType`
  - `WORKFLOW_STEP_TYPE`, `WORKFLOW_CATEGORY`, `WORKFLOW_CATEGORY_LABEL` as const
  - `FlowNode` — 캔버스 노드 (id, type, label, x, y)
  - `FlowEdge` — 노드 연결선 (id, fromId, toId)

### 페이지
- [x] `src/pages/WorkflowDesignerPage/index.tsx` — 갤러리 뷰 (카드 그리드 + 편집 버튼 → 플로우 빌더 이동)
- [x] `src/pages/WorkflowDesignerPage/FlowCanvas.tsx` — 비주얼 플로우 에디터 컴포넌트
- [x] `src/pages/WorkflowBuilderPage/index.tsx` — 플로우 빌더 전용 페이지 (FlowCanvas 호스팅)

### 라우터
- [x] `src/App.tsx` — `/workflow-designer` 라우트 추가
- [x] `src/App.tsx` — `/workflow-builder` 라우트 추가

### 네비게이션
- [x] `src/components/layout/TopNav.tsx` — "에이전트" 드롭다운에 "워크플로우 설계" 추가
- [x] `src/components/layout/TopNav.tsx` — "에이전트" 드롭다운에 "플로우 빌더" 추가 (path: /workflow-builder)
- [x] `src/components/layout/Sidebar.tsx` — "워크플로우 설계" 사이드바 항목 추가

---

## UI 구성

### 갤러리 뷰 (기본, /workflow-designer)

#### 헤더
- 아이콘 + 제목 + 서브타이틀
- 단계 타입 범례 (색상별 아이콘 + 레이블)
- 활성 워크플로우 카운트
- **"플로우 빌더" 버튼** → `/workflow-builder`로 페이지 이동

#### 필터 탭
- 전체 | 검색 | 분석 | 자동화 | 커스텀

#### 워크플로우 카드 (3열 그리드)
- 이름 + **"편집" 버튼** (hover 시 표시) + 토글 스위치
- "편집" 클릭 → `workflowToFlow()` 변환 후 `/workflow-builder`로 state 전달
- 설명, 단계 플로우 시각화, 카테고리 배지, 예상 시간, 실행 횟수

#### 선택된 워크플로우 상세 패널
- 선택된 워크플로우 이름 + 메타 정보
- **"캔버스에서 편집" 버튼** → `workflowToFlow()` 변환 후 `/workflow-builder`로 state 전달
- 큰 단계 아이콘 + 레이블 시각화 (가로 플로우)

#### 활성 워크플로우 요약 섹션
- 활성화된 워크플로우를 뱃지 형태로 나열

### 플로우 빌더 페이지 (/workflow-builder)

#### WorkflowBuilderPage
- `useLocation().state`로 초기 워크플로우 데이터 수신 (갤러리 편집 진입 시)
- `initialName`, `initialNodes`, `initialEdges`를 FlowCanvas에 전달
- 저장 시 `flowToSteps()` 위상 정렬 변환 실행
- 저장 결과 상단 배너 표시 (이름, 단계 수)
- Mock: console.log + 배너, 추후 API 연동 예정

#### flowToSteps() (위상 정렬)
- in-degree 0 노드부터 edge 순서로 traverse
- 연결되지 않은 노드: x 좌표 기준 추가

---

### FlowCanvas 에디터 (`FlowCanvas.tsx`)

#### 툴바
- "갤러리로" 뒤로가기 버튼
- 워크플로우 이름 인라인 편집 input
- 노드/연결 카운트 표시
- "노드 삭제" 버튼 (선택된 노드 있을 때)
- "저장" 버튼 (저장 시 2초 녹색 blink)

#### 왼쪽 팔레트
- 7가지 노드 타입 드래그 가능 카드 (입력/검색/코드/LLM/조건/출력/API)
- 각 노드에 설명 텍스트 (desc) 포함
- 드래그 안내 텍스트

#### 캔버스 (중앙)
- 도트 그리드 배경 (24px 간격)
- 노드를 팔레트에서 드래그앤드롭으로 추가
- 노드 드래그로 위치 변경
- 빈 상태 안내 메시지

#### SVG 엣지 레이어
- 베지어 커브 연결선 (보라색, 화살표 마커)
- 점선 pending 연결선 (연결 중 상태)
- 연결선 클릭으로 삭제

#### 노드
- 왼쪽 포트 (○): 클릭 시 연결 완료
- 오른쪽 포트 (○): 클릭 시 연결 시작
- 노드 선택 시 ring 강조
- 연결 중 대상 노드 포트 강조 (scale-125)

#### 오른쪽 도움말 패널
- 조작법 안내 (노드 추가/이동/연결/삭제)
- 연결 중 상태 힌트 박스
- Mock 모드 안내 (이벤트 콘솔 출력)

---

## 이벤트 시스템 (Mock)

`dispatchFlowEvent()` 함수로 모든 UI 이벤트를 콘솔에 출력.
추후 서버 연동 시 이 함수만 API 호출로 교체.

| 이벤트 | payload | 설명 |
|--------|---------|------|
| `NODE_ADDED` | `FlowNode` | 노드 추가 |
| `NODE_MOVED` | `{ id, x, y }` | 노드 이동 완료 |
| `NODE_DELETED` | `{ id }` | 노드 삭제 |
| `EDGE_CREATED` | `FlowEdge` | 연결선 생성 |
| `EDGE_DELETED` | `{ id }` | 연결선 삭제 |
| `WORKFLOW_SAVED` | `{ name, nodes, edges }` | 저장 |

---

## 저장 로직 (Mock)

FlowNode[] + FlowEdge[] → WorkflowStep[] 변환:
1. 위상 정렬 (in-degree 0인 노드부터 edge 순서 따라가기)
2. 연결되지 않은 노드는 x 좌표 기준 정렬로 추가
3. 새 워크플로우: workflows 목록에 추가 (category: custom)
4. 기존 워크플로우 편집: name + steps 업데이트

---

## 단계 타입 색상 체계
| 타입 | 색상 | 레이블 |
|------|------|--------|
| input | zinc-400 | 입력 |
| search | sky-400 | 검색 |
| code | amber-400 | 코드 |
| llm | violet-500 | LLM |
| condition | orange-400 | 조건 |
| output | emerald-400 | 출력 |
| api | pink-400 | API |

---

## Mock 워크플로우 목록 (8개)
| ID | 이름 | 카테고리 | 단계 수 | 기본 활성 |
|----|------|---------|--------|--------|
| rag-qa | RAG Q&A | search | 4 | O |
| web-analysis | 웹 검색 분석 | search | 4 | O |
| doc-summary | 문서 요약 | analysis | 4 | X |
| code-review | 코드 리뷰 | analysis | 4 | X |
| email-automation | 이메일 자동화 | automation | 4 | O |
| data-pipeline | 데이터 분석 파이프라인 | analysis | 5 | X |
| alert-monitor | 이상 감지 알림 | automation | 4 | X |
| custom-workflow | 커스텀 워크플로우 | custom | 3 | X |

---

## API 연동 (예정)
- `GET /api/workflows` → 워크플로우 목록 조회
- `PATCH /api/workflows/{id}/toggle` → 활성화 토글
- `POST /api/workflows` → 새 워크플로우 생성
- `PUT /api/workflows/{id}` → 워크플로우 업데이트
- WebSocket or SSE → 실시간 플로우 이벤트 전송
- 현재: 로컬 useState + `dispatchFlowEvent()` Mock
