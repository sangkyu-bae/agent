# LangSmith 추적 설정 및 환경 변수 관리

## 개요
LangSmith 추적 기능을 활성화/비활성화하고 환경 변수를 설정하는 유틸리티 함수들입니다.

## 주요 기능

### 1. langsmith() 함수
LangSmith 추적을 설정하는 함수입니다.

**매개변수:**
- `project_name` (str, optional): LangSmith 프로젝트 이름
- `set_enable` (bool, default=True): 추적 활성화 여부

**동작 방식:**
1. 환경 변수에서 API 키 확인 (`LANGCHAIN_API_KEY` 또는 `LANGSMITH_API_KEY`)
2. 더 긴 API 키를 선택하여 사용
3. API 키가 없으면 로그 메시지 출력 후 종료
4. 추적이 활성화되면:
   - `LANGSMITH_ENDPOINT`: https://api.smith.langchain.com
   - `LANGSMITH_TRACING`: "true"
   - `LANGSMITH_PROJECT`: 프로젝트명 설정
5. 비활성화되면 `LANGSMITH_TRACING`을 "false"로 설정

**사용 예시:**
```python
# 추적 활성화
langsmith(project_name="my-project")

# 추적 비활성화
langsmith(set_enable=False)
```

### 2. env_variable() 함수
환경 변수를 설정하는 간단한 헬퍼 함수입니다.

**매개변수:**
- `key` (str): 환경 변수 키
- `value` (str): 환경 변수 값

**사용 예시:**
```python
env_variable("API_KEY", "your-api-key-here")
```

## 로깅
- 모듈 레벨 로거 사용: `logging.getLogger(__name__)`
- 추적 시작 시 프로젝트명 로깅
- API 키 미설정 시 정보 메시지 출력

## 주의사항
- API 키는 반드시 환경 변수로 미리 설정되어 있어야 합니다
- `LANGCHAIN_API_KEY`와 `LANGSMITH_API_KEY` 중 하나만 있어도 동작합니다
- 프로젝트명은 추적 활성화 시 필수입니다