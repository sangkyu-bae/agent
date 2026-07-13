# doc-extractor-slot-add-fix Design

> Plan: [doc-extractor-slot-add-fix.plan.md](../../01-plan/features/doc-extractor-slot-add-fix.plan.md)
>
> 문서추출기 "슬롯 직접 추가" 무반응 수정 — 검증을 확정 시점과 동일한 정규화 매칭으로
> 교체(FR-01)하고, 결과 피드백을 추가 버튼 인접 인라인으로 이동(FR-02~04)한다.

## 1. 개요

| 항목 | 내용 |
|------|------|
| 대상 기능 | Agent Builder → 문서추출기 설정 → 슬롯 직접 추가 |
| 변경 파일 | `src/utils/documentTemplate.ts`, `src/components/agent-builder/DocumentExtractorConfigPanel.tsx` + 각 테스트 |
| 백엔드 변경 | 없음 (`TemplateTokenPolicy`가 저장 직전 정합 재검증 유지) |
| 설계 원칙 | 추가 시점 검증 = 확정 시점 토큰화와 **동일한 매칭 경로** 공유 |

---

## 2. 설계 상세

### 2-1. `documentTemplate.ts` — `htmlContainsText` 헬퍼 (FR-01)

기존 내부 함수(`parseDoc`, `buildTextIndex`, `findRange`)를 조합만 하는 공개 헬퍼.
**기존 로직은 일절 수정하지 않는다.**

```typescript
// 위치: tokenizeHtml 정의 바로 아래 (§D2 매칭 계열 함수 군집 유지)

/**
 * 수동 슬롯 추가 검증용(FR-01): 정규화 텍스트 기준으로 본문에 텍스트가
 * 존재하는지 확인. tokenizeHtml과 동일한 매칭 경로(buildTextIndex+findRange)를
 * 쓰므로 "추가 통과 = 확정 시 토큰화 가능"이 보장된다.
 */
export const htmlContainsText = (html: string, text: string): boolean =>
  findRange(buildTextIndex(parseDoc(html)), text) !== null;
```

동작 계약 (findRange에 위임):

| 입력 | 결과 |
|------|------|
| 숫자 엔티티 한글 (`&#xae08;` 등) vs 화면 표기 문자열 | `true` (DOMParser 해소) |
| span 분절 (`<span>5억</span><span> 원</span>`) | `true` (텍스트 노드 연결) |
| 연속 공백/개행 차이 | `true` (공백 축약 정규화) |
| 빈 문자열 / 공백만 | `false` (`findRange`가 null 반환) |
| 본문에 없는 텍스트 | `false` |

### 2-2. `DocumentExtractorConfigPanel.tsx` — 검증 교체 + 인라인 피드백 (FR-01~04)

#### 상태 추가

```typescript
interface AddSlotFeedback {
  type: 'error' | 'success';
  message: string;
}

const [addSlotFeedback, setAddSlotFeedback] = useState<AddSlotFeedback | null>(null);
```

- 수동 추가의 검증/결과는 **전역 `errorMessage`를 더 이상 사용하지 않는다**
  (전역 위치는 업로드/재추천/확정 에러 전용으로 유지 — 원인 2 재발 방지).

#### `handleAddSlot` 변경

```typescript
const handleAddSlot = () => {
  if (!draft) return;
  const label = newSlotLabel.trim();
  const sample = newSlotSample.trim();
  if (!label || !sample) {
    setAddSlotFeedback({
      type: 'error',
      message: '항목명과 예시값(문서 내 실제 텍스트)을 모두 입력해주세요.',
    });
    return;
  }
  if (!htmlContainsText(draft.html, sample)) {           // ← FR-01: includes 대체
    setAddSlotFeedback({
      type: 'error',
      message:
        '예시값을 문서에서 찾지 못했습니다. 미리보기에 보이는 텍스트를 그대로 입력해주세요.',
    });
    return;
  }
  const key = generateSlotKey(draft.slots.map((s) => s.key));
  const slot: TemplateSlot = {
    key,
    label,
    slot_type: newSlotType,
    description: '',
    fill_hint: '',
    sample_value: sample,
  };
  onChange({
    ...draft,
    slots: [...draft.slots, slot],
    confirmed: false,
    htmlSkeleton: '',
  });
  setAddSlotFeedback({
    type: 'success',
    message: `'${label}' 슬롯이 추가되었습니다.`,       // ← FR-03
  });
  setNewSlotLabel('');
  setNewSlotSample('');
  setNewSlotType('value');
};
```

#### 입력 변경 시 피드백 초기화

항목명/예시값 입력 `onChange`에서 이전 피드백 제거 (다음 시도 준비):

```typescript
onChange={(e) => {
  setNewSlotLabel(e.target.value);   // 예시값 입력도 동일 패턴
  setAddSlotFeedback(null);
}}
```

#### 렌더링 — "슬롯 직접 추가" 박스 내부, 버튼 행 아래 (FR-02)

```tsx
{/* 슬롯 직접 추가 박스(border-dashed div) 안, flex-wrap 행 다음 */}
{addSlotFeedback && (
  <p
    role={addSlotFeedback.type === 'error' ? 'alert' : 'status'}
    className={`mt-1.5 text-[11.5px] ${
      addSlotFeedback.type === 'error' ? 'text-red-500' : 'text-emerald-600'
    }`}
  >
    {addSlotFeedback.message}
  </p>
)}
```

- 색상 토큰: 기존 관례 준수 — 에러 `text-red-500`, 성공 `text-emerald-600`
  (확정 배너 `text-emerald-700`/`bg-emerald-50`과 동일 계열).
- `role="alert"`(에러)/`role="status"`(성공)로 스크린리더 즉시 공지 + 테스트 셀렉터 겸용.
- 다른 액션(재요청/확정/초기화) 실행 시 피드백은 유지해도 무해하나,
  `handleReset`에서는 `setAddSlotFeedback(null)`로 함께 초기화한다.

#### 변경하지 않는 것

- `draft.html`을 검증 대상으로 유지 (확정 `tokenizeHtml` 대상과 동일해야 함 — Plan §7 리스크 2)
- 전역 `errorMessage`/`noticeMessage` 렌더 위치 및 업로드/재추천/확정 흐름
- `generateSlotKey`, 슬롯 목록/제거/라벨 편집 로직

---

## 3. 테스트 설계 (TDD — Red 먼저)

### 3-1. `src/utils/documentTemplate.test.ts` — `describe('htmlContainsText')`

기존 `tokenizeHtml` D4 케이스와 동일 fixture 패턴 사용:

| # | 케이스 | 입력 | 기대 |
|---|--------|------|------|
| 1 | 평문 존재 | `'<p>금액: 5억 원</p>'`, `'5억 원'` | `true` |
| 2 | 숫자 엔티티 한글 | `'<p><span>&#xae08; 500,000,000&#xc6d0;</span></p>'`, `'금 500,000,000원'` | `true` |
| 3 | span 분절 | `'<p><span>500,</span><span>000,000원</span></p>'`, `'500,000,000원'` | `true` |
| 4 | 연속 공백 정규화 | `'<p>금   500,000,000원</p>'`, `'금 500,000,000원'` | `true` |
| 5 | 미존재 텍스트 | `'<p>내용 없음</p>'`, `'5억 원'` | `false` |
| 6 | 빈/공백 문자열 | `'<p>금액</p>'`, `'   '` | `false` |

### 3-2. `DocumentExtractorConfigPanel.test.tsx` — G2 describe 수정/추가

| # | 유형 | 케이스 | 어서션 |
|---|------|--------|--------|
| 1 | 수정 | 예시값 미존재 시 에러 | `onChange` 미호출 + `role="alert"`에 `/예시값을 문서에서 찾지 못했습니다/` 표시 (기존 문구 어서션 교체) |
| 2 | 신규 | 엔티티/분절 html에서 화면 표기 예시값으로 추가 성공 | `draftFixture({ html: '<p><span>&#xb2f4;</span><span>&#xb2f9;&#xc790;: &#xae40;&#xacfc;&#xc7a5;</span></p>' })`에 `'담당자: 김과장'` 입력 → `onChange` 호출, `slots` 2개 |
| 3 | 신규 | 추가 성공 피드백 | 성공 추가 후 `role="status"`에 `/'담당자' 슬롯이 추가되었습니다/` + 입력 필드 초기화 확인 |
| 4 | 신규 | 입력 변경 시 피드백 소거 | 에러 표시 → 예시값 입력 타이핑 → `queryByRole('alert')`가 `null` |
| 5 | 유지 | 기존 "문서에 있는 예시값으로 수동 슬롯을 추가한다" | 어서션 변경 없음 (평문 fixture는 새 매칭도 통과) |

> 실행: `npx vitest run --pool=threads src/utils/documentTemplate.test.ts src/components/agent-builder/DocumentExtractorConfigPanel.test.tsx`
> (Windows forks 풀 워커 기동 타임아웃 회피 — 프로젝트 알려진 이슈)

---

## 4. 구현 순서

1. **[Red]** `documentTemplate.test.ts`에 `htmlContainsText` describe 추가 → 실패 확인
2. **[Green]** `documentTemplate.ts`에 `htmlContainsText` export 추가
3. **[Red]** 패널 테스트 수정/추가 (§3-2) → 실패 확인
4. **[Green]** `DocumentExtractorConfigPanel.tsx` 수정
   - import에 `htmlContainsText` 추가
   - `AddSlotFeedback` 상태 도입, `handleAddSlot` 교체, 입력 onChange 피드백 소거, 렌더 추가, `handleReset` 소거
5. **[Refactor]** 전체 관련 테스트 + `npm run type-check` 통과 확인

---

## 5. 완료 기준 (Plan §8 매핑)

| Plan 기준 | Design 검증 방법 |
|-----------|-----------------|
| `htmlContainsText` export + 단위 테스트 | §3-1 6케이스 통과 |
| 실문서에서 수동 슬롯 추가 성공 | §3-2 #2 (엔티티/분절 fixture) + dev 서버 수동 확인 |
| 에러가 버튼 인접 표시 | §3-2 #1 (`role="alert"` 박스 내부 렌더) |
| 성공 피드백 표시 | §3-2 #3 |
| 확정 시 제외되지 않음 | 매칭 경로 공유로 구조 보장 + 수동 확인 (업로드→추가→확정) |
| 테스트 전체 통과 | §3-2 명령 + 기존 케이스 회귀 없음 |
