# KIWI-001: Kiwi 형태소 분석기 모듈

> Task ID: KIWI-001
> 의존성: LOG-001
> 상태: Done

---

## 목적

`kiwipiepy` 기반 한국어 형태소 분석기를 독립 모듈로 구현한다.
청킹(CHUNK-001), ES 키워드 색인(CHUNK-IDX-001) 파이프라인에
플러그인 방식으로 연결할 수 있도록 **인터페이스 중심으로 설계**한다.

---

## 아키텍처

```
MorphAnalyzerInterface (domain/morph)
        │
        ▼
KiwiMorphAnalyzer (infrastructure/morph)
        │
        ├── kiwipiepy.Kiwi.tokenize(text)
        └── MorphToken 변환 (form, tag.name, start, len)

# 향후 연결 포인트
KiwiKeywordExtractor(KeywordExtractorInterface)  ← CHUNK-IDX-001 대체
    └── KiwiMorphAnalyzer.extract_nouns(text)
```

---

## 구현 대상

### Domain Layer
| 파일 | 설명 |
|------|------|
| `src/domain/morph/schemas.py` | `MorphToken`, `MorphAnalysisResult` Value Object |
| `src/domain/morph/interfaces.py` | `MorphAnalyzerInterface` ABC + `extract_nouns()` 편의 메서드 |

### Infrastructure Layer
| 파일 | 설명 |
|------|------|
| `src/infrastructure/morph/kiwi_morph_analyzer.py` | `KiwiMorphAnalyzer` — kiwipiepy 래퍼 |

---

## 형태소 품사 태그 (kiwipiepy)

| 태그 | 분류 | 예시 |
|------|------|------|
| NNG | 일반 명사 | 정책, 금융 |
| NNP | 고유 명사 | 한국, 서울 |
| NNB | 의존 명사 | 것, 수 |
| VV | 동사 | 하다, 분석하다 |
| VA | 형용사 | 좋다, 크다 |
| MAG | 일반 부사 | 매우, 빠르게 |

---

## 도메인 스키마

```python
@dataclass(frozen=True)
class MorphToken:
    surface: str   # 표면형 (token.form)
    pos: str       # 품사 태그명 (token.tag.name: "NNG", "VV", ...)
    start: int     # 시작 문자 위치
    length: int    # 문자 길이

@dataclass(frozen=True)
class MorphAnalysisResult:
    tokens: tuple[MorphToken, ...]   # 분석된 전체 토큰
    text: str                        # 원본 텍스트

    @property
    def nouns(self) -> list[MorphToken]:      # NNG | NNP | NNB
    @property
    def verbs(self) -> list[MorphToken]:      # VV
    @property
    def adjectives(self) -> list[MorphToken]: # VA
    @property
    def noun_surfaces(self) -> list[str]:     # 명사 표면형 목록
```

---

## 인터페이스

```python
class MorphAnalyzerInterface(ABC):
    @abstractmethod
    def analyze(self, text: str) -> MorphAnalysisResult:
        """형태소 분석 수행 — 구현 필수."""

    def extract_nouns(self, text: str) -> list[str]:
        """명사 표면형 반환 — analyze() 기반 편의 메서드."""
        return self.analyze(text).noun_surfaces
```

---

## 테스트 파일

| 테스트 파일 | 대상 | mock |
|------------|------|------|
| `tests/domain/morph/test_schemas.py` | MorphToken, MorphAnalysisResult (9 케이스) | ❌ |
| `tests/infrastructure/morph/test_kiwi_morph_analyzer.py` | KiwiMorphAnalyzer (11 케이스) | ✅ |

총 20 테스트 케이스.

---

## 향후 연결 포인트

| 확장 | 설명 |
|------|------|
| `KiwiKeywordExtractor` | `KeywordExtractorInterface` 구현, `extract_nouns()` → top-N 반환 |
| 청킹 전 정규화 | `KiwiMorphAnalyzer`로 원형 복원(lemmatization) 후 청킹 |
| 불용어 필터 | 도메인 특화 불용어 목록 주입 지원 |

---

## LOG-001 로깅 체크리스트

- [x] `KiwiMorphAnalyzer`는 stateless — 로거 주입 불필요 (infrastructure util)
- [ ] UseCase 레벨에서 사용 시 LoggerInterface 주입 (향후)

---

## 완료 기준

- [x] `MorphToken`, `MorphAnalysisResult` Value Object (frozen dataclass)
- [x] `MorphAnalyzerInterface` ABC + `extract_nouns()` 편의 메서드
- [x] `KiwiMorphAnalyzer` — kiwipiepy Kiwi 래퍼
- [x] 전체 20 테스트 통과
- [x] `pyproject.toml`에 `kiwipiepy>=0.17.0` 추가
