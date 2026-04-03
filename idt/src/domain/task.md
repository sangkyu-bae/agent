# Tasks

## 🎯 In Progress

### CHAT-001: 멀티턴 대화 관리 시스템 (DB + Repository + DTO)

- **상태**: 대기 중
- **목적**: user_id와 session_id 기준으로 대화 흐름을 유지하고, 특정 턴 초과 시 요약 저장
- **기술 스택**: FastAPI, SQLAlchemy (ORM), MySQL

---

#### 📦 1. 데이터베이스 모델

##### 1-1. Conversation 테이블
- **목적**: 현재 진행 중인 대화 메시지 저장
- **파일**: `app/models/conversation.py`
- **컬럼**:
  - [ ] id (PK, Auto Increment)
  - [ ] user_id (사용자 식별)
  - [ ] session_id (채팅방/세션 식별)
  - [ ] role (user / assistant)
  - [ ] content (메시지 내용)
  - [ ] turn_number (대화 턴 번호)
  - [ ] created_at
- **세부 태스크**:
  - [ ] SQLAlchemy 모델 정의
  - [ ] 인덱스 설정 (user_id, session_id 복합 인덱스)

##### 1-2. ConversationSummary 테이블
- **목적**: 특정 턴 초과 시 대화 요약 저장
- **파일**: `app/models/conversation_summary.py`
- **컬럼**:
  - [ ] id (PK, Auto Increment)
  - [ ] user_id
  - [ ] session_id
  - [ ] summary_content (요약 내용)
  - [ ] start_turn (요약 시작 턴)
  - [ ] end_turn (요약 끝 턴)
  - [ ] created_at
- **세부 태스크**:
  - [ ] SQLAlchemy 모델 정의
  - [ ] 인덱스 설정

---

#### 📄 2. DTO (Pydantic Schemas)

- **파일**: `app/schemas/conversation.py`

##### 2-1. Conversation DTO
- [ ] ConversationCreate (role, content 등 입력용)
- [ ] ConversationResponse (조회 응답용)
- [ ] ConversationListResponse (목록 조회용)

##### 2-2. ConversationSummary DTO
- [ ] ConversationSummaryCreate (summary_content, start_turn, end_turn)
- [ ] ConversationSummaryResponse (조회 응답용)

---

#### 🗄️ 3. Repository (CRUD)

##### 3-1. ConversationRepository
- **파일**: `app/repositories/conversation_repository.py`
- **메서드**:
  - [ ] create(user_id, session_id, role, content, turn_number) → 메시지 저장
  - [ ] get_by_id(id) → 단일 메시지 조회
  - [ ] get_by_session(user_id, session_id) → 세션별 대화 목록 조회
  - [ ] update(id, content) → 메시지 수정
  - [ ] delete(id) → 메시지 삭제
  - [ ] delete_by_session(user_id, session_id) → 세션 대화 전체 삭제

##### 3-2. ConversationSummaryRepository
- **파일**: `app/repositories/conversation_summary_repository.py`
- **메서드**:
  - [ ] create(user_id, session_id, summary_content, start_turn, end_turn) → 요약 저장
  - [ ] get_by_id(id) → 단일 요약 조회
  - [ ] get_by_session(user_id, session_id) → 세션별 요약 목록 조회
  - [ ] get_latest_by_session(user_id, session_id) → 최신 요약 조회
  - [ ] update(id, summary_content) → 요약 수정
  - [ ] delete(id) → 요약 삭제

---

#### 📁 예상 폴더 구조
```
app/
├── models/
│   ├── __init__.py
│   ├── conversation.py
│   └── conversation_summary.py
├── schemas/
│   ├── __init__.py
│   └── conversation.py
├── repositories/
│   ├── __init__.py
│   ├── conversation_repository.py
│   └── conversation_summary_repository.py
└── database.py (DB 연결 설정)
```

---

#### ✅ 완료 조건
- [ ] MySQL 연결 확인
- [ ] 테이블 마이그레이션 완료
- [ ] Repository CRUD 동작 테스트
- [ ] DTO 유효성 검사 동작 확인

---

#### 📝 메모
- 요약 트리거 로직 (몇 턴에서 요약할지)은 Service 레이어에서 구현 예정
- 추후 CHAT-002에서 Service 레이어 구현
```

---