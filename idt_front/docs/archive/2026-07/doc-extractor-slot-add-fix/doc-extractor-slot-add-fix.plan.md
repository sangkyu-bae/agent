# doc-extractor-slot-add-fix Plan

> Agent Builder 문서추출기 설정에서 "슬롯 직접 추가" 버튼 클릭 시 아무 반응이 없는 문제 수정
> (검증 로직 오탐 + 에러 피드백 비가시 이중 결함)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | 문서추출기 수동 슬롯 추가 무반응 수정 |
| 작성일 | 2026-07-06 |
| 예상 소요 | 2~3시간 (유틸 헬퍼 + 패널 수정 + 테스트) |
| 영향 범위 | `documentTemplate.ts`, `DocumentExtractorConfigPanel.tsx` + 각 테스트 파일 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| Problem | 슬롯 직접 추가에서 "추가"를 눌러도 화면상 아무 일도 일어나지 않아 기능이 죽은 것처럼 보임 |
| Solution | 검증을 확정(tokenize)과 동일한 정규화 텍스트 매칭으로 교체하고, 결과 피드백(에러/성공)을 버튼 바로 옆에 표시 |
| Function UX Effect | 추천이 놓친 항목을 사용자가 직접 등록할 수 있게 되고, 실패 시 원인·해결 방법이 즉시 보임 |
| Core Value | 추가 시점 검증과 확정 시점 토큰화가 같은 매칭 규칙을 공유 → "추가는 됐는데 확정에서 제외" / "추가 자체가 불가" 불일치 제거 |

---

## 1. 배경 및 목표

### AS-IS (현재 문제)

`/agent-builder` → 문서추출기 도구 설정 모달 → "슬롯 직접 추가"에서 항목명·예시값을 입력하고
**추가** 버튼을 눌러도 슬롯이 추가되지 않고, 사용자에게는 아무 피드백도 보이지 않는다.

### TO-BE (목표)

1. 문서에 실제로 보이는 텍스트를 예시값으로 입력하면 슬롯이 정상 추가된다.
2. 검증 실패 시(빈 값 / 예시값 미존재) 에러 메시지가 **추가 버튼 바로 아래**에 즉시 표시된다.
3. 추가 성공 시에도 성공 피드백이 같은 위치에 표시되어 "눌렀는데 무반응" 상황이 원천적으로 사라진다.

---

## 2. 원인 분석

### 원인 1 — 기능 결함: 원시 문자열 `includes` 검증이 실문서에서 항상 실패

`DocumentExtractorConfigPanel.tsx:188`:

```typescript
if (!draft.html.includes(sample)) {
  setErrorMessage('예시값이 문서 본문에 없습니다. ...');
  return;
}
```

그러나 이 프로젝트의 `documentTemplate.ts:1-5` 상단 주석에 이미 실측 결과가 명시되어 있다:

> MCP pdf_to_html 출력(한글 숫자 엔티티·span 분절·white-space:pre 공백 보존 — PoC 실측)은
> **문자열 완전일치가 항상 실패**하므로, DOMParser로 엔티티를 해소한 뒤
> 텍스트 노드 연결 문자열을 정규화(공백 축약)해 매칭한다.

즉:
- 화면에 `대출금액`으로 보이는 텍스트가 HTML 원문에서는 `&#xB300;&#xCD9C;...`(숫자 엔티티)이거나 `<span>대</span><span>출</span>...`(span 분절)로 저장됨
- 사용자가 미리보기에서 보이는 대로 입력한 예시값은 `draft.html.includes(...)` 원시 매칭에 **거의 항상 걸리지 않음**
- 확정 시점의 `tokenizeHtml`·미리보기의 `buildPreviewHtml`은 정규화 매칭(`buildTextIndex` + `findRange`)을 쓰는데, **수동 추가 검증만 원시 매칭**이라 자기들끼리 규칙이 어긋나 있음

> 단위 테스트가 통과하는 이유: 테스트 fixture의 html은 엔티티/분절 없는 평문이라 `includes`가 성공한다. 실제 MCP 변환 산출물에서만 재현되는 결함.

### 원인 2 — UX 결함: 에러 메시지가 뷰포트 밖에 렌더링

- 에러 표시 위치: 패널 최상단 (`DocumentExtractorConfigPanel.tsx:282-284`)
- 추가 버튼 위치: 미리보기 iframe(**45vh**) + 슬롯 목록 **아래쪽**
- 렌더 컨텍스트: `DocumentExtractorConfigModal` — `size="full"`, `h-[80vh]`, `scroll="body"`

사용자가 추가 버튼을 누르는 시점에는 패널 상단이 스크롤 밖에 있으므로, 검증 실패로
`setErrorMessage`가 호출되어도 **화면에 보이는 변화가 전혀 없음** → "아무 일도 안 일어난다"로 인지.

### 종합

실문서에서는 원인 1로 검증이 항상 실패하고, 원인 2로 그 실패조차 보이지 않는다.
두 가지를 함께 고쳐야 문제가 해소된다.

---

## 3. 요구사항

| ID | 요구사항 | 우선순위 |
|----|---------|:---:|
| FR-01 | 수동 슬롯 예시값 검증을 확정 시점과 동일한 **정규화 텍스트 매칭**으로 교체 | P1 |
| FR-02 | 검증 실패 에러를 "슬롯 직접 추가" 박스 **내부(버튼 근처)** 에 즉시 표시 | P1 |
| FR-03 | 추가 성공 시 성공 피드백을 같은 위치에 표시 (예: `'담당자' 슬롯이 추가되었습니다`) | P2 |
| FR-04 | 에러 문구에 해결 힌트 포함 (미리보기에 보이는 텍스트를 그대로 입력하라는 안내) | P2 |

> 사용자 요청의 "팝업창이라도"는 **버튼 인접 인라인 메시지**로 충족한다.
> 별도 alert/다이얼로그는 입력 흐름을 끊으므로 채택하지 않되, 인라인 표시로 부족하다고
> 판단되면 Design 단계에서 `ConfirmDialog` 재사용을 재검토한다.

---

## 4. 수정 계획

### 4-1. `utils/documentTemplate.ts` — 정규화 매칭 헬퍼 export (FR-01)

기존 내부 함수 `parseDoc` + `buildTextIndex` + `findRange`를 조합한 공개 헬퍼 추가:

```typescript
/** 수동 슬롯 추가 검증용: 정규화 텍스트 기준으로 본문에 텍스트가 존재하는지 확인. */
export const htmlContainsText = (html: string, text: string): boolean =>
  findRange(buildTextIndex(parseDoc(html)), text) !== null;
```

- 확정 시점 `tokenizeHtml`과 **완전히 같은 매칭 경로**를 타므로,
  "추가 시 통과 = 확정 시 토큰화 가능"이 구조적으로 보장된다.

### 4-2. `DocumentExtractorConfigPanel.tsx` — 검증 교체 + 피드백 위치 이동 (FR-01~04)

1. `handleAddSlot`의 `draft.html.includes(sample)` → `htmlContainsText(draft.html, sample)`
2. 수동 추가 전용 로컬 상태 도입: `addSlotFeedback: { type: 'error' | 'success'; message: string } | null`
   - 검증 실패 → error 세팅 (패널 상단 `errorMessage`는 사용하지 않음)
   - 추가 성공 → success 세팅 + 입력 필드 초기화 (기존 동작 유지)
   - 입력값 변경 시 피드백 초기화
3. "슬롯 직접 추가" 박스 내부, 버튼 행 아래에 피드백 렌더링:
   - error: `text-red-500`, success: `text-emerald-600` (기존 토큰 관례 준수)
4. 에러 문구 개선(FR-04):
   - 예시값 미존재: `예시값을 문서에서 찾지 못했습니다. 미리보기에 보이는 텍스트를 그대로 입력해주세요.`

### 4-3. 테스트 (TDD — Red → Green)

**`utils/documentTemplate.test.ts`** (신규 케이스):
- 숫자 엔티티로 저장된 한글 텍스트를 화면 표기 문자열로 찾는다
- span 분절된 텍스트(`<span>5억</span> <span>원</span>`)를 찾는다
- 공백 차이(연속 공백/개행)를 무시하고 찾는다
- 본문에 없는 텍스트는 `false`

**`DocumentExtractorConfigPanel.test.tsx`** (수정 + 신규):
- (수정) 기존 "예시값이 문서에 없으면" 케이스 — 새 에러 문구·인라인 위치로 어서션 갱신
- (신규) 엔티티/분절 fixture html에서 화면 표기 예시값으로 추가가 성공한다
- (신규) 추가 성공 시 성공 메시지가 "슬롯 직접 추가" 박스 안에 표시된다
- (신규) 입력값을 다시 수정하면 이전 피드백이 사라진다

---

## 5. 영향 범위

| 파일 | 변경 유형 |
|------|-----------|
| `src/utils/documentTemplate.ts` | 헬퍼 1개 export 추가 (기존 로직 변경 없음) |
| `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` | 검증 호출 교체 + 로컬 피드백 상태/렌더링 |
| `src/utils/documentTemplate.test.ts` | 신규 케이스 추가 |
| `src/components/agent-builder/DocumentExtractorConfigPanel.test.tsx` | 어서션 갱신 + 신규 케이스 |

백엔드 변경 없음 — 저장 직전 정합성은 기존 `TemplateTokenPolicy`가 그대로 재검증한다.

---

## 6. 검증 방법

1. `npx vitest run --pool=threads src/utils/documentTemplate.test.ts src/components/agent-builder/DocumentExtractorConfigPanel.test.tsx`
2. 수동 확인 (dev 서버):
   - `/agent-builder` → 문서추출기 → 실제 PDF 업로드
   - 미리보기에 보이는 텍스트를 예시값으로 입력 후 **추가** → 슬롯 목록에 추가되는지 확인
   - 존재하지 않는 텍스트 입력 후 **추가** → 버튼 아래 에러 메시지가 스크롤 없이 보이는지 확인
   - 추가한 슬롯으로 **슬롯 확정** → 확정 시 제외되지 않는지(원인 1 해소 검증) 확인

---

## 7. 리스크

| 리스크 | 확률 | 대응 |
|--------|:---:|------|
| 정규화 매칭 완화로 의도치 않은 위치가 먼저 매칭 | 낮음 | `tokenizeHtml`과 동일 규칙(첫 출현 치환)이므로 기존 확정 동작과 동일 수준 — 미리보기 하이라이트로 사용자가 위치 확인 가능 |
| 미리보기는 `previewHtml`(레이아웃)인데 검증 대상은 `html`(시맨틱)이라 두 문서의 텍스트가 다를 가능성 | 낮음 | 검증 대상은 확정 토큰화 대상인 `html`이 맞음. 불일치 시 FR-04 에러 문구가 안내. 실측 불일치가 확인되면 후속 과제로 분리 |
| 기존 테스트 문구 어서션 파손 | 확실 | 계획에 어서션 갱신 포함 (4-3) |

---

## 8. 완료 기준

- [ ] `htmlContainsText` 유틸 export + 단위 테스트 통과 (엔티티/분절/공백 케이스)
- [ ] 실문서(MCP 변환 산출물)에서 미리보기 표기 텍스트로 수동 슬롯 추가 성공
- [ ] 검증 실패 시 에러가 추가 버튼 인접 위치에 스크롤 없이 표시
- [ ] 추가 성공 피드백 표시
- [ ] 수동 추가 슬롯이 확정 시 `missingSlots`로 제외되지 않음
- [ ] 관련 테스트 전체 통과 (`--pool=threads`)
