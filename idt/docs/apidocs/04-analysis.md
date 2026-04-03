# 엑셀 분석 API (Self-Corrective Agent)

> **태그**: `Excel Analysis`
> **Base Path**: `/api/v1/analysis`

---

## 개요

엑셀 파일과 질문을 함께 전송하면 AI가 데이터를 분석하여 답변합니다.

### 내부 처리 흐름

```
엑셀 파일 업로드
     ↓
pandas로 데이터 파싱
     ↓
Claude AI 분석 (최대 3회 시도)
     ↓
할루시네이션 검증 (사실 확인)
     ↓  실패 시
웹 검색(Tavily) + Python 코드 실행으로 보완
     ↓
최종 답변 반환
```

**Self-Corrective** 방식: 답변 품질이 낮으면 자동으로 웹 검색이나 코드 실행으로 보완하며 최대 3회 재시도합니다.

---

## 엔드포인트

### 엑셀 파일 분석

**`POST /api/v1/analysis/excel`**

#### 요청 (multipart/form-data)

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `file` | File | ✅ | - | 분석할 엑셀 파일 (`.xlsx`, `.xls`) |
| `query` | string | ✅ | - | 분석 질문 (자연어) |
| `user_id` | string | ❌ | `anonymous` | 요청자 ID |

#### 응답 (200 OK)

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "2024년 분기별 매출 합계는?",
  "final_answer": "2024년 분기별 매출 합계는 1분기 1.2억원, 2분기 1.5억원, 3분기 1.8억원, 4분기 2.1억원입니다.",
  "is_successful": true,
  "total_attempts": 2,
  "attempts": [
    {
      "attempt_number": 1,
      "confidence_score": 0.65,
      "hallucination_score": 0.3,
      "used_web_search": false,
      "timestamp": "2024-03-18T10:30:00"
    },
    {
      "attempt_number": 2,
      "confidence_score": 0.92,
      "hallucination_score": 0.05,
      "used_web_search": true,
      "timestamp": "2024-03-18T10:30:05"
    }
  ],
  "executed_code": "import pandas as pd\ndf = pd.read_excel(...)\nresult = df.groupby('quarter')['sales'].sum()",
  "code_output": {"Q1": 120000000, "Q2": 150000000, "Q3": 180000000, "Q4": 210000000}
}
```

#### 응답 필드 상세

| 필드 | 설명 |
|------|------|
| `final_answer` | 최종 답변 텍스트 |
| `is_successful` | 품질 기준 통과 여부 |
| `total_attempts` | 실제 시도 횟수 (최대 3회) |
| `attempts` | 각 시도별 상세 기록 |
| `attempts[].confidence_score` | 답변 신뢰도 (0.0~1.0, 높을수록 좋음) |
| `attempts[].hallucination_score` | 할루시네이션 점수 (0.0~1.0, 낮을수록 좋음) |
| `attempts[].used_web_search` | 웹 검색 사용 여부 |
| `executed_code` | 실행된 Python 코드 (코드 실행 시) |
| `code_output` | 코드 실행 결과 (코드 실행 시) |

#### 예제

```bash
curl -X POST "http://localhost:8000/api/v1/analysis/excel" \
  -F "file=@financial_data.xlsx" \
  -F "query=전체 매출 대비 각 제품군의 비율을 계산해줘" \
  -F "user_id=analyst_001"
```

---

## 재시도 로직 상세

```
1차 시도: Claude AI가 엑셀 데이터로만 분석
   → confidence < 임계값이면 2차 시도

2차 시도: 웹 검색(Tavily)으로 외부 정보 보완
   → 여전히 부족하면 3차 시도

3차 시도: Python 코드 직접 실행으로 정확한 계산
   → 3회 후 is_successful=false로 응답
```

## 주의사항

- 파일 크기가 클수록 처리 시간이 증가합니다
- 복잡한 수식이 있는 경우 코드 실행으로 자동 계산합니다
- 웹 검색은 외부 API(Tavily) 비용이 발생합니다
