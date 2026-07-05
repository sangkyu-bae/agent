# Logging & Error Tracking Rules (LOG-001)

> 원본: CLAUDE.md §9

---

## 기본 원칙

모든 모듈은 이 규칙을 따른다.

- 모든 API 요청/응답은 **자동 로깅**된다
- 에러 발생 시 **스택 트레이스 필수 기록**
- **request_id**로 요청 전체 흐름 추적 가능

---

## 로깅 필수 항목

### API 요청 로그
```json
{
    "request_id": "uuid",
    "method": "POST",
    "endpoint": "/api/v1/documents/upload",
    "query_params": {},
    "body": {"user_id": "..."},
    "headers": {"content-type": "..."}
}
```

### API 응답 로그
```json
{
    "request_id": "uuid",
    "status_code": 200,
    "process_time_ms": 1500
}
```

### 에러 로그 (스택 트레이스 필수)
```json
{
    "request_id": "uuid",
    "error": {
        "type": "ValueError",
        "message": "Invalid PDF format",
        "stacktrace": "Traceback (most recent call last):..."
    }
}
```

---

## 로깅 적용 규칙

| 상황 | 로그 레벨 | 필수 포함 |
|------|----------|-----------|
| API 요청 수신 | INFO | request_id, method, endpoint |
| API 정상 응답 | INFO | request_id, status_code, process_time_ms |
| 비즈니스 에러 | WARNING | request_id, error_type, message |
| 시스템 에러 | ERROR | request_id, error_type, message, **stacktrace** |
| 치명적 에러 | CRITICAL | 위 전부 + 알림 트리거 |

---

## 새 모듈 개발 시 로깅 체크리스트

- [ ] LoggerInterface 주입 받아 사용
- [ ] 주요 처리 시작/완료 INFO 로그
- [ ] 예외 발생 시 ERROR 로그 + 스택 트레이스
- [ ] request_id 컨텍스트 전파
- [ ] 민감 정보 마스킹 (password, token, api_key)

```python
# 모든 서비스/노드에서 로깅 패턴
class SomeService:
    def __init__(self, logger: LoggerInterface):
        self._logger = logger
    
    async def process(self, request_id: str, data: dict):
        self._logger.info("Processing started", request_id=request_id, data_keys=list(data.keys()))
        
        try:
            result = await self._do_work(data)
            self._logger.info("Processing completed", request_id=request_id)
            return result
        except Exception as e:
            self._logger.error("Processing failed", exception=e, request_id=request_id)
            raise
```

---

## 금지 사항

- ❌ print() 사용 금지 (logger 사용)
- ❌ 스택 트레이스 없는 에러 로그 금지
- ❌ request_id 없는 로그 금지 (API 컨텍스트 내)
- ❌ 민감 정보 평문 로깅 금지
