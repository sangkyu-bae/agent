# pii-masking Design Document

> **Summary**: 외부 LLM 경계에서 한국 PII를 가역 마스킹/복원하는 프레임워크 독립 엔진 모듈 설계
>
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Date**: 2026-06-30
> **Status**: Draft
> **Planning Doc**: [pii-masking.plan.md](../../01-plan/features/pii-masking.plan.md)

---

## 0. Plan 결정 + Open Question 확정

| 항목 | 결정 |
|------|------|
| 모듈 형태 | 커스텀 마스킹 모듈 (프레임워크 독립, Thin DDD) |
| PII 종류 | 주민등록번호 / 휴대폰·전화 / 이메일 / 계좌 / 카드 |
| 마스킹 전략 | 가역 마스킹 (placeholder 치환 + 원복) |
| 적용 지점 | 사용자 입력 · 검색결과·tool · LLM 응답 |
| **OQ1 카드/계좌** | **카드 = 빌트인형 패턴(자릿수+Luhn) / 계좌 = 한국 휴리스틱 → 별도 타입 분리** |
| **OQ2 token_map 스코프** | **session_id 단위로 묶음 (멀티턴 동일 PII 일관성)** |
| **OQ3 응답 redact 표기** | **`[REDACTED_PHONE]`처럼 타입 노출** |

---

## 1. Overview

### 1.1 Design Goals

- 외부 LLM 호출 경계에서 원본 PII가 나가지 않게 한다.
- placeholder 일관성으로 LLM 추론·RAG 답변 품질을 유지한다.
- LangGraph/LangChain 버전·경로(create_react_agent vs create_agent)에 **의존하지 않는** 순수 모듈로 만든다.
- 이번 산출물은 **엔진 + 포트 인터페이스**까지. 그래프 실제 배선은 후속 plan.

### 1.2 Design Principles

- 단일 책임: detector(탐지) / service(오케스트레이션) / port(부착) 분리
- domain은 외부 의존성 0 (정규식·표준 라이브러리만)
- token_map은 메모리 범위, 비영속·비로깅 (보안)
- config 기반 토글, 하드코딩 금지

---

## 2. Architecture

### 2.1 Component Diagram

```
                         ┌───────────────────────────────────────┐
                         │           application                 │
  入: user query         │   PiiMaskingService                   │
  入: retrieved docs ───▶│   - mask(text, ctx)  → MaskingResult  │──▶ 외부 LLM
                         │   - unmask(text, vault) → text        │
  出: LLM answer    ◀────│   - redact_unmapped(text) (출력단)    │◀──
                         └───────────────┬───────────────────────┘
                                         │ uses
                  ┌──────────────────────┴───────────────────────┐
                  ▼                                               ▼
        ┌──────────────────────┐                     ┌──────────────────────┐
        │      domain          │                     │   infrastructure     │
        │  PiiType, PiiMatch   │  detector impl 주입   │  RegexPiiDetector    │
        │  PiiDetectorPort     │◀────────────────────│  (RRN/phone/email/   │
        │  PiiMaskingPolicy    │                     │   card/account)      │
        │  TokenVault (VO)     │                     └──────────────────────┘
        │  PiiMaskingPort      │
        └──────────────────────┘
```

### 2.2 Data Flow (가역 마스킹)

```
① 입력/검색결과
   text ──mask()──▶ PiiDetector.detect() → [PiiMatch...]
                 → Policy 검증(오탐 필터) → placeholder 치환
                 → TokenVault[session_id] 에 {placeholder: original} 누적
                 → masked_text (외부 LLM 전달)

② LLM 응답
   answer ──unmask(vault)──▶ vault의 placeholder를 원본으로 역치환
          ──redact_unmapped()──▶ vault에 없는 신규 PII는 [REDACTED_<TYPE>] 단방향 처리
                              → 사용자에게 반환
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| PiiMaskingService (application) | PiiDetectorPort, PiiMaskingPolicy, TokenVault, LoggerInterface (domain) | 흐름 제어 |
| RegexPiiDetector (infrastructure) | domain.pii_masking.schemas/interfaces | 정규식 탐지 구현 |
| domain.pii_masking | (없음 — re, dataclass만) | 규칙·VO |

> domain → infrastructure 참조 금지. detector 구현체는 application 조립 시 주입.

---

## 3. Data Model

### 3.1 도메인 타입 (`src/domain/pii_masking/schemas.py`)

```python
class PiiType(str, Enum):
    RRN = "rrn"            # 주민등록번호
    PHONE = "phone"        # 휴대폰/전화
    EMAIL = "email"
    CARD = "card"          # 신용/체크카드 (자릿수 + Luhn)
    ACCOUNT = "account"    # 한국 은행 계좌 (휴리스틱)

@dataclass(frozen=True)
class PiiMatch:
    pii_type: PiiType
    text: str        # 원본 매칭 문자열
    start: int
    end: int

@dataclass(frozen=True)
class MaskingResult:
    masked_text: str
    placeholders: dict[str, str]   # {placeholder: original} (이번 호출에서 새로 만든 것)

@dataclass
class TokenVault:
    """session 범위 placeholder↔원본 매핑 (양방향)."""
    _by_placeholder: dict[str, str] = field(default_factory=dict)
    _by_original: dict[str, str] = field(default_factory=dict)   # 동일 원본→동일 placeholder
    _counters: dict[PiiType, int] = field(default_factory=dict)
    # get_or_create_placeholder(pii_type, original) -> str
    # restore(text) -> text  (placeholder 역치환)
```

### 3.2 placeholder 포맷

```
[<TYPE>_<n>]   예) [RRN_1], [PHONE_1], [EMAIL_2], [CARD_1], [ACCOUNT_1]
```
- 영숫자·대괄호 고정 → LLM 응답에서 변형 위험 최소화
- 동일 원본값 → 동일 placeholder (TokenVault._by_original 역인덱스)
- 출력단 신규 PII redact 표기: `[REDACTED_PHONE]` 등 (OQ3)

### 3.3 TokenVault 스코프 (OQ2)

- 키: **session_id** (멀티턴 동일 PII 일관성)
- 이번 모듈은 `TokenVaultRegistry`(in-memory dict[session_id, TokenVault])만 제공
- 영속화(체크포인터/Redis)는 후속 plan — 인터페이스(`TokenVaultStorePort`)만 정의해 교체 가능하게 둔다

---

## 4. 탐지 규칙 (Detector 명세)

| PiiType | 패턴/휴리스틱 | 오탐 저감(Policy) |
|---------|--------------|------------------|
| RRN | `\d{6}[-\s]?\d{7}` | 앞 6자리 생년월일 유효성 + 7번째 성별코드(1~4,5~8) 약식 검증 |
| PHONE | `01[016789][-\s]?\d{3,4}[-\s]?\d{4}`, 지역번호 `0\d{1,2}-\d{3,4}-\d{4}` | 길이/접두 검증 |
| EMAIL | RFC 약식 `[\w.+-]+@[\w-]+\.[\w.-]+` | TLD 최소 길이 |
| CARD | `\b\d(?:[-\s]?\d){12,18}\b` (13~19자리, Visa16/Amex15/Diners14) | **Luhn 체크섬** 통과 시에만 |
| ACCOUNT | 한국 계좌 휴리스틱: `\d{2,6}-\d{2,6}-\d{2,6}` 또는 10~14 연속 숫자 | CARD/RRN/PHONE 매칭 우선 제외 후 잔여만 |

**탐지 우선순위(겹침 처리)**: RRN → CARD(Luhn) → PHONE → EMAIL → ACCOUNT.
- 위치(span) 겹치면 우선순위 높은 타입이 점유, 잔여 구간만 다음 detector에 노출.
- ACCOUNT는 가장 느슨 → 항상 마지막, 다른 타입에 잡히지 않은 숫자열만 후보.

---

## 5. API / 포트 시그니처

> HTTP 엔드포인트 추가 없음 (내부 모듈). 외부 노출은 포트 인터페이스.

### 5.1 PiiMaskingPort (`src/domain/pii_masking/interfaces.py`)

```python
class PiiMaskingPort(Protocol):
    def mask(self, text: str, session_id: str) -> str:
        """입력/검색결과 마스킹. vault에 매핑 누적 후 masked_text 반환."""
    def unmask(self, text: str, session_id: str) -> str:
        """응답 원복 + 미매핑 PII redact."""
```

### 5.2 PiiDetectorPort

```python
class PiiDetectorPort(Protocol):
    def detect(self, text: str) -> list[PiiMatch]: ...
```

### 5.3 PiiMaskingService (`src/application/pii_masking/pii_masking_service.py`)

```python
class PiiMaskingService:
    # 검증(PiiMaskingPolicy)은 detector(RegexPiiDetector) 내부에 위치 → 생성자에 policy 인자 없음.
    def __init__(self, detector: PiiDetectorPort, registry: TokenVaultRegistry,
                 logger: LoggerInterface, config: PiiMaskingConfig): ...
    def mask(self, text: str, session_id: str) -> str: ...
    def unmask(self, text: str, session_id: str) -> str: ...
```

---

## 6. Error Handling

| 상황 | 처리 |
|------|------|
| `PII_MASKING_ENABLED=false` | mask/unmask는 입력 그대로 통과 (no-op) |
| detector 정규식 예외 | `error` 로그(스택 포함) 후 **fail-closed**: `mask`는 `[PII_MASKING_FAILED]` 반환(원문 미노출), `unmask` redact 단계는 원문 유지하되 고아 placeholder 2차 방어 |
| unmask 후 잔존(고아) placeholder 발견 | `_redact_orphan_placeholders`가 WARN 로그(개수만) + `[REDACTED_<TYPE>]` 대체 |
| session_id 없음(빈 문자열) | registry가 해당 키로 임시 vault를 생성해 동작(멀티턴 일관성만 미보장) |

> 로깅 규칙(LOG-001): `LoggerInterface` 사용, 원본 PII·token_map 값 **로그 미기록**(placeholder 키/카운트만).

---

## 7. Security Considerations

- [x] 외부 LLM 전달 전 원본 PII 치환 (입력+검색결과)
- [x] token_map(vault) 비영속·비로깅
- [x] 출력단 미매핑 PII 2차 redact (방어적, OQ3 타입 노출)
- [x] config 토글로 긴급 비활성 가능
- [ ] (후속) vault 영속 시 암호화 — `secret_cipher.py` 패턴 재사용 검토

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | detector 타입별 탐지/오탐, Luhn, 우선순위 겹침 | pytest |
| Unit | placeholder 일관성(동일 원본→동일), 카운터 증가 | pytest |
| Unit | mask→unmask round-trip 정합성 | pytest |
| Unit | 출력단 미매핑 PII redact 표기 | pytest |
| Unit | config off 시 no-op | pytest |

### 8.2 Test Cases (Key)

- [ ] Happy: "홍길동 901010-1234567 010-1234-5678" → `[RRN_1]`,`[PHONE_1]` 치환, unmask 원복
- [ ] 일관성: 같은 주민번호 2회 등장 → 동일 `[RRN_1]`
- [ ] 멀티턴: 동일 session_id 다음 호출에서도 동일 placeholder
- [ ] Luhn: 유효 카드번호만 CARD, 임의 16자리는 ACCOUNT 후보로
- [ ] 겹침: 카드번호가 PHONE/ACCOUNT 패턴과 겹쳐도 CARD 우선
- [ ] 오탐: 일반 4자리 연도/금액 숫자는 미마스킹
- [ ] Edge: 응답에 vault 없는 새 전화번호 → `[REDACTED_PHONE]`
- [ ] off: `PII_MASKING_ENABLED=false`면 입력 그대로

---

## 9. Clean Architecture

### 9.1 Layer 배치

| Component | Layer | Location |
|-----------|-------|----------|
| PiiType, PiiMatch, MaskingResult, TokenVault, TokenVaultRegistry | Domain | `src/domain/pii_masking/schemas.py` |
| PiiDetectorPort, PiiMaskingPort, TokenVaultStorePort | Domain | `src/domain/pii_masking/interfaces.py` |
| PiiMaskingPolicy (오탐 검증/우선순위) | Domain | `src/domain/pii_masking/policies.py` |
| 정규식 패턴 상수 | Domain | `src/domain/pii_masking/patterns.py` |
| PiiMaskingService | Application | `src/application/pii_masking/pii_masking_service.py` |
| 요청/결과 DTO | Application | `src/application/pii_masking/schemas.py` |
| RegexPiiDetector | Infrastructure | `src/infrastructure/pii_masking/regex_detectors.py` |

### 9.2 Import 규칙 준수

```
Application(Service) ──▶ Domain(port/policy/vo)
Infrastructure(RegexPiiDetector) ──▶ Domain(schemas/interfaces)
Domain ──▶ (없음)
```
- detector 주입: `main.py` 팩토리에서 `RegexPiiDetector` → `PiiMaskingService` 조립 (기존 DI 패턴)
- domain은 `re`, `dataclass`만 import (verify-architecture 통과 대상)

---

## 10. Coding Convention Reference

### 10.1 Naming

| Target | Rule | Example |
|--------|------|---------|
| 클래스 | PascalCase | `PiiMaskingService`, `RegexPiiDetector` |
| 함수 | snake_case | `detect()`, `get_or_create_placeholder()` |
| 상수 | UPPER_SNAKE_CASE | `RRN_PATTERN`, `REDACT_PREFIX` |
| 모듈 파일 | snake_case.py | `pii_masking_service.py` |

### 10.3 Environment Variables (`src/config.py` Settings 추가)

| 변수(snake_case 필드) | 기본값 | 용도 |
|----------------------|--------|------|
| `pii_masking_enabled` | `True` | 전역 on/off |
| `pii_masking_types` | `"rrn,phone,email,card,account"` | 활성 타입 (쉼표) |
| `pii_masking_output_redact` | `True` | 응답단 미매핑 PII redact 여부 |

> `.env.example`에도 동일 키 추가. 하드코딩 금지(CLAUDE.md §3).

---

## 11. Implementation Guide

### 11.1 File Structure (신규)

```
src/domain/pii_masking/
├── __init__.py
├── schemas.py        # PiiType, PiiMatch, MaskingResult, TokenVault, TokenVaultRegistry
├── interfaces.py     # PiiDetectorPort, PiiMaskingPort, TokenVaultStorePort
├── patterns.py       # 정규식 상수
└── policies.py       # PiiMaskingPolicy (Luhn, 생년월일 검증, 우선순위/겹침)

src/application/pii_masking/
├── __init__.py
├── schemas.py
└── pii_masking_service.py

src/infrastructure/pii_masking/
├── __init__.py
└── regex_detectors.py

tests/
├── domain/pii_masking/test_policies.py        # Luhn, RRN 검증, 우선순위
├── domain/pii_masking/test_token_vault.py     # 일관성/원복
├── application/pii_masking/test_service.py     # mask/unmask round-trip, off no-op
└── infrastructure/pii_masking/test_regex_detectors.py  # 타입별 탐지/오탐
```

### 11.2 Implementation Order (TDD: Red→Green→Refactor)

1. [ ] `domain/pii_masking/schemas.py` + `patterns.py` (타입·정규식 상수)
2. [ ] `test_policies.py` 작성(Red) → `policies.py` 구현(Luhn/RRN/우선순위)
3. [ ] `test_regex_detectors.py`(Red) → `infrastructure/regex_detectors.py` 구현
4. [ ] `test_token_vault.py`(Red) → `TokenVault`/`Registry` 구현(일관성·원복)
5. [ ] `test_service.py`(Red) → `PiiMaskingService.mask/unmask` 구현
6. [ ] `src/config.py` Settings 3필드 + `.env.example` 반영
7. [ ] `main.py` 팩토리 DI 조립 (port 노출만, 그래프 배선은 후속)
8. [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd`

### 11.3 후속 plan 연결 지점 (배선 미포함, 참고)

- 입력/검색결과: `src/application/rag_agent/tools.py:150` `_format_results` 반환 직전 `mask()`
- 응답: `src/application/agent_builder/run_agent_use_case.py` final answer 노드(≈ :500-576) 직후 `unmask()`
- general chat: `src/application/general_chat/use_case.py` astream 출력 집계 지점
- v2 미들웨어 경로: `MiddlewareBuilder`의 `PIIMiddleware(detector=RegexPiiDetector.detect)` custom detector 주입

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-30 | 초안 (Plan 결정 + OQ1~3 확정 반영) | 배상규 |
