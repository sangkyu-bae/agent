# EXCEL-EXPORT-001: pandas Excel 파일 생성 공통 모듈 + LangChain Tool

- **상태**: 완료
- **목적**: pandas + openpyxl을 사용하여 테이블 데이터를 Excel(.xlsx) 파일로 생성하는 공통 모듈. LangChain BaseTool로 Agent에서 직접 호출 가능
- **기술 스택**: Python, pandas, openpyxl, LangChain BaseTool, FastAPI, asyncio.to_thread
- **의존성**: LOG-001 (LoggerInterface)

---

## 구현 파일

| 레이어 | 파일 |
|--------|------|
| Domain | `src/domain/excel_export/schemas.py` |
| Domain | `src/domain/excel_export/interfaces.py` |
| Infrastructure | `src/infrastructure/excel_export/pandas_excel_exporter.py` |
| Infrastructure | `src/infrastructure/excel_export/excel_export_tool.py` ← **LangChain Tool** |
| Application | `src/application/use_cases/excel_export_use_case.py` |
| API | `src/api/routes/excel_export_router.py` |
| Tests | `tests/domain/excel_export/test_schemas.py` |
| Tests | `tests/infrastructure/excel_export/test_pandas_excel_exporter.py` |
| Tests | `tests/infrastructure/excel_export/test_excel_export_tool.py` |
| Tests | `tests/application/use_cases/test_excel_export_use_case.py` |
| Tests | `tests/api/test_excel_export_router.py` |

---

## API

```
POST /api/v1/excel/export
```

**Request Body (JSON):**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_id` | str | ✅ | 요청 사용자 ID |
| `sheets` | list[SheetBody] | ✅ | 시트 목록 (최소 1개) |
| `filename` | str | - | 파일명 (기본값: `output.xlsx`, `.xlsx` 자동 추가) |

**SheetBody:**

| 필드 | 타입 | 설명 |
|------|------|------|
| `columns` | list[str] | 컬럼 헤더 목록 |
| `rows` | list[list] | 데이터 행 목록 |
| `sheet_name` | str | 시트 이름 (기본값: `Sheet1`) |

**Response:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`

---

## LangChain Tool 사용법

```python
from src.infrastructure.excel_export.excel_export_tool import ExcelExportTool

tool = ExcelExportTool()

# LangGraph Agent에 등록
tools = [tool]

# 직접 호출
path = tool._run(
    columns=["이름", "점수"],
    rows=[["Alice", 90], ["Bob", 85]],
    filename="결과.xlsx",
    sheet_name="성적표",
    output_dir="/tmp/reports",
)
# → "/tmp/reports/결과.xlsx" 반환

# 다중 시트
path = tool._run(
    columns=["이름"],
    rows=[["Alice"]],
    sheet_name="Sheet1",
    extra_sheets=[
        {"sheet_name": "Sheet2", "columns": ["값"], "rows": [[42]]}
    ],
)
```

**Tool 스펙:**
- `name`: `"excel_export"`
- `args_schema`: `ExcelExportInput`
- 반환값: 저장된 Excel 파일의 절대 경로 (str)
- 오류 시: `"ERROR: Excel 생성 실패 - ..."` 문자열 반환 (Agent가 처리 가능)

---

## 도메인 스키마

### ExcelSheetData

```python
class ExcelSheetData(BaseModel):
    sheet_name: str = "Sheet1"   # 공백이면 ValidationError
    columns: list[str]            # 빈 리스트이면 ValidationError
    rows: list[list[Any]] = []    # 빈 rows 허용
```

### ExcelExportRequest

```python
class ExcelExportRequest(BaseModel):
    filename: str       # .xlsx 없으면 자동 추가
    sheets: list[ExcelSheetData]  # 최소 1개
    request_id: str
    user_id: str
```

### ExcelExportResult

```python
class ExcelExportResult(BaseModel):
    filename: str
    user_id: str
    request_id: str
    excel_bytes: bytes
    size_bytes: int
    sheet_count: int
    exporter_used: str  # "pandas+openpyxl"
```

---

## Application UseCase

```python
class ExcelExportUseCase:
    def __init__(self, exporter: ExcelExporterInterface, logger: LoggerInterface)
    async def export(self, request: ExcelExportRequest) -> ExcelExportResult
```

- `exporter.export()`는 sync → `asyncio.to_thread()`로 비동기 래핑
- LOG-001 준수: 시작/완료 INFO, 예외 ERROR + exception= 키워드

---

## 의존성 주입 (`main.py` 연동)

```python
from src.api.routes.excel_export_router import get_excel_export_use_case, router
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter

app.include_router(router)
app.dependency_overrides[get_excel_export_use_case] = lambda: ExcelExportUseCase(
    exporter=PandasExcelExporter(),
    logger=get_app_logger(),
)
```

---

## 테스트 현황

| 테스트 파일 | 테스트 수 | 통과 |
|------------|-----------|------|
| `tests/domain/excel_export/test_schemas.py` | 11 | ✅ |
| `tests/infrastructure/excel_export/test_pandas_excel_exporter.py` | 8 | ✅ |
| `tests/infrastructure/excel_export/test_excel_export_tool.py` | 9 | ✅ |
| `tests/application/use_cases/test_excel_export_use_case.py` | 6 | ✅ |
| `tests/api/test_excel_export_router.py` | 5 | ✅ |
| **합계** | **39** | **100%** |

---

## LOG-001 준수 체크리스트

- [x] LoggerInterface 주입 받아 사용 (UseCase)
- [x] Tool 내부에서 get_logger() 사용
- [x] 시작/완료 INFO 로그 (request_id 포함)
- [x] 예외 발생 시 ERROR 로그 + `exception=` 키워드
- [x] request_id 모든 로그에 포함
- [x] print() 사용 없음
- [x] logging 예약 키 충돌 방지 (`output_filename` 사용)

---

## pyproject.toml 의존성

pandas, openpyxl은 이미 포함되어 있음 (기존 EXCEL-001 의존성).
