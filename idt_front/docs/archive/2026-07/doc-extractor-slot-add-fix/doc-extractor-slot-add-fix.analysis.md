# doc-extractor-slot-add-fix Gap Analysis

> Check 단계 — Design 문서 vs 구현 코드 비교 (gap-detector, 2026-07-06)
>
> - Design: [doc-extractor-slot-add-fix.design.md](../../02-design/features/doc-extractor-slot-add-fix.design.md)
> - Plan: [doc-extractor-slot-add-fix.plan.md](../../01-plan/features/doc-extractor-slot-add-fix.plan.md)

## 결과 요약

| 항목 | 값 |
|------|-----|
| **Match Rate** | **98%** (23✅ + 1⚠️×0.5 / 24항목) |
| 판정 | **PASS** (≥ 90%) |
| Missing Features | 없음 |
| Added Features | 없음 |
| Gap | Low 1건 (테스트 입력 표기 차이 — 기능 동등) |

## 1. 항목별 매칭 테이블

| # | Design 항목 | 상태 | 근거 (파일:라인) |
|---|------------|:----:|-----------------|
| **§2-1** htmlContainsText | | | |
| 1 | export 형태 `findRange(buildTextIndex(parseDoc(html)), text) !== null` | ✅ | documentTemplate.ts:180-181 (설계 코드와 동일) |
| 2 | tokenizeHtml 정의 바로 아래 배치 | ✅ | tokenizeHtml 173행 종료 → 175-181 헬퍼 |
| 3 | 기존 로직(parseDoc/buildTextIndex/findRange) 미수정 | ✅ | 53-54, 61-86, 88-94 원형 유지 |
| **§2-2** 검증 교체 + 인라인 피드백 | | | |
| 4 | `AddSlotFeedback` 인터페이스 | ✅ | DocumentExtractorConfigPanel.tsx:23-26 |
| 5 | `addSlotFeedback` 상태 | ✅ | 52-54 |
| 6 | handleAddSlot에서 `htmlContainsText(draft.html, sample)` 사용 | ✅ | 204 |
| 7 | 에러 문구 ① 빈 값 | ✅ | 198 |
| 8 | 에러 문구 ② 미존재 (해결 힌트 포함) | ✅ | 207-208 |
| 9 | 성공 문구 `'{label}' 슬롯이 추가되었습니다.` | ✅ | 229 |
| 10 | 항목명 onChange 피드백 소거 | ✅ | 419-422 |
| 11 | 예시값 onChange 피드백 소거 | ✅ | 430-433 |
| 12 | role=alert/status, 박스 내부 flex 행 다음 렌더 | ✅ | 455-466 |
| 13 | 색상 text-red-500 / text-emerald-600 | ✅ | 459-461 |
| 14 | handleReset에서 setAddSlotFeedback(null) | ✅ | 267 |
| 15 | 수동 추가 경로에서 전역 errorMessage 미사용 | ✅ | handleAddSlot 191-234 |
| **§2-2** 변경하지 않는 것 | | | |
| 16 | draft.html 검증 대상 유지 | ✅ | 204 |
| 17 | 전역 errorMessage/noticeMessage 렌더 위치 유지 | ✅ | 303-308 |
| 18 | generateSlotKey/슬롯 목록/제거/라벨 편집 유지 | ✅ | 212, 171-189, 355-399 |
| **§3-1** 유틸 테스트 | | | |
| 19 | 6케이스 (평문/엔티티/분절/공백/미존재/빈문자열) | ✅ | documentTemplate.test.ts:102-130 |
| **§3-2** 패널 테스트 | | | |
| 20 | #1 에러 어서션 교체 (role=alert + 새 문구) | ✅ | DocumentExtractorConfigPanel.test.tsx:260-276 |
| 21 | #2 엔티티/분절 fixture 추가 성공 | ⚠️ | 279-296 — 입력값 표기만 설계와 상이 (Gap 참조) |
| 22 | #3 성공 피드백 + 입력 초기화 | ✅ | 298-315 |
| 23 | #4 입력 변경 시 피드백 소거 | ✅ | 317-331 |
| 24 | #5 기존 평문 추가 케이스 유지 | ✅ | 240-258 |

## 2. Gap 목록

| 심각도 | 항목 | 설명 | 조치 |
|:------:|------|------|------|
| Low | §3-2 #2 | Design은 예시값 입력을 `'담당자: 김과장'` 단일 문자열로 명시했으나 구현은 label=`'담당자'` + 예시값=`'김과장'` 분리. 두 텍스트 모두 fixture에 존재하고 엔티티/분절 매칭 검증 목적은 동일하게 충족 (예시값 매칭을 라벨과 분리해 오히려 정밀). | 조치 불요 (기능 동등) |

## 3. 동적 검증 (Do 단계에서 확인 완료)

| 검증 | 결과 |
|------|------|
| `npx vitest run --pool=threads` 유틸+패널 | ✅ 47/47 통과 |
| agent-builder 전체 회귀 | ✅ 18파일 130/130 통과 |
| `npm run type-check` | ✅ 통과 |
| TDD Red 선행 확인 | ✅ 유틸 6건·패널 4건 의도 실패 후 구현 |

## 4. 종합 판정

**PASS — Match Rate 98%.** FR-01(정규화 매칭)·FR-02(버튼 인접 인라인)·FR-03(성공 피드백)·FR-04(해결 힌트) 전부 구현 확인. "변경하지 않는 것" 3항목 모두 보존되어 회귀 위험 낮음.

잔여 항목: 실제 PDF로 dev 서버 수동 확인(Plan §6 시나리오 2) — 코드/테스트 검증 범위 밖의 최종 인수 확인.

다음 단계: `/pdca report doc-extractor-slot-add-fix`
