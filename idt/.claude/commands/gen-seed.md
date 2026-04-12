# gen-seed

DB 마이그레이션 파일을 분석해서 테스트용 seed INSERT SQL을 생성합니다.
API 문서가 함께 제공되면 즉시 생성하고, 없으면 구조만으로 판단 후 필요시 요청합니다.

## Usage

```
/gen-seed <migration_file> [api_doc_file]
```

## Arguments

- `$MIGRATION_FILE` — (필수) `db/migration/` 폴더 기준 파일명 (예: `AUTH-001.sql`)
- `$API_DOC_FILE` — (선택) `docs/api/` 폴더 기준 파일명 (예: `auth.md`)

## Instructions

다음 단계를 순서대로 수행하세요.

### Step 1: 파일 읽기

**마이그레이션 파일 읽기 (항상 수행)**

`db/migration/$MIGRATION_FILE` 파일을 읽어서 아래 정보를 파악하세요.

- 테이블 목록과 각 컬럼 (이름, 타입, NOT NULL, DEFAULT, ENUM 값 등)
- PRIMARY KEY, UNIQUE KEY, FOREIGN KEY 제약
- AUTO_INCREMENT 컬럼 (INSERT에서 생략 가능한 컬럼)
- ENUM 타입의 허용값 목록

**API 문서 읽기 (파라미터가 있을 때만 수행)**

`$API_DOC_FILE` 이 제공된 경우: `docs/api/$API_DOC_FILE` 을 읽어서 아래 정보를 파악하세요.

- 도메인의 주요 역할/권한 종류 (예: role: user, admin)
- 상태값 종류 (예: status: pending, approved, rejected)
- 비즈니스 로직상 필요한 시드 데이터 힌트 (예: 관리자 계정, 초기 데이터)

### Step 2: 생성 가능 여부 판단

마이그레이션 파일을 읽은 후, **사용자의 요청**과 **테이블 구조**만으로 INSERT를 만들 수 있는지 판단하세요.

**즉시 생성 가능한 경우 (Step 3으로 이동):**
- API 문서가 이미 제공됨 (파라미터 2개)
- 요청이 구체적이고 테이블 구조만으로 충분히 유추 가능
  - 예: "admin 계정 만들어줘" → users 테이블에 role ENUM('user','admin') 존재 → 생성 가능

**API 문서가 필요한 경우 (사용자에게 안내):**
- 요청이 모호하고 테이블 구조만으로는 어떤 데이터를 넣어야 할지 알 수 없는 경우
- 아래 메시지로 안내하세요:

```
테이블 구조는 파악했는데, 어떤 seed 데이터가 필요한지 명확히 하려면
API 문서가 있으면 더 정확하게 만들 수 있어요.

다음 중 하나를 선택해주세요:
1. `/gen-seed $MIGRATION_FILE <api_doc_file>` — API 문서도 같이 전달
2. 원하는 데이터를 직접 설명해주세요 (예: "admin 계정 1개, 일반 유저 2개")
```

### Step 3: INSERT SQL 생성

파악한 정보를 바탕으로 INSERT SQL을 생성하세요.

**생성 규칙:**

1. **AUTO_INCREMENT 컬럼은 생략** — id는 DB가 자동 부여
2. **DEFAULT 값이 있는 컬럼은 생략 가능** — 단, 명시적으로 넣는 게 가독성에 좋으면 포함
3. **FOREIGN KEY 순서 준수** — 참조되는 테이블 먼저 INSERT
4. **비밀번호는 bcrypt 해시 형태로** — 실제 해시값 사용
   - 평문 `admin1234` → `$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj4J/HS.iK9e` (예시)
   - 주석으로 평문 비밀번호 명시: `-- password: admin1234`
5. **ENUM 값은 실제 허용값만 사용**
6. **여러 로우가 필요하면 한 INSERT에 VALUES 여러 개**로 묶기
7. **테이블 단위로 섹션 구분** — 주석으로 어떤 데이터인지 설명

**출력 포맷:**

```sql
-- =============================================
-- Seed: {사용자 요청 요약}
-- Generated from: {migration_file} {+ api_doc_file if used}
-- =============================================

-- {테이블명}: {이 테이블에 넣는 데이터 설명}
INSERT INTO {table_name} ({col1}, {col2}, ...) VALUES
  ({val1}, {val2}, ...),  -- {row 설명}
  ({val1}, {val2}, ...);  -- {row 설명}
```

### Step 4: 결과 출력 후 안내

INSERT SQL 출력 후 아래를 간단히 안내하세요.

- 삽입된 데이터 요약 (몇 개 테이블, 몇 개 row)
- 비밀번호 평문이 있으면 명시
- 필요시 추가 seed 요청 방법 안내

---

## 예시

### 예시 1: 파라미터 1개 + 명확한 요청

```
/gen-seed AUTH-001.sql
사용자: admin 계정 만들어줘
```

→ `db/migration/AUTH-001.sql` 읽기 → `users.role ENUM('user','admin')` 확인 → 즉시 생성

### 예시 2: 파라미터 2개

```
/gen-seed AUTH-001.sql auth.md
사용자: 테스트용 seed 만들어줘
```

→ 마이그레이션 + API 문서 모두 읽기 → 도메인 파악 → admin 1개 + 일반유저 2개 등 적절히 생성

### 예시 3: 파라미터 1개 + 모호한 요청

```
/gen-seed AUTH-001.sql
사용자: 테스트 데이터 만들어줘
```

→ 마이그레이션 읽기 → 요청이 모호함 → API 문서 요청 또는 구체적인 설명 요청