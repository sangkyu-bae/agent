# Testing & Common Task Rules

> 원본: CLAUDE.md §5, §6

---

## Testing Rules

- 모든 use-case는 테스트 필수
- domain 테스트는 mock 금지
- infrastructure 테스트는 mock 또는 test container 사용
- Retriever / Chunking / Parent Requery는 케이스 테스트 필수

---

## 새로운 기능 추가 절차

1. domain 정책 존재 여부 확인
2. application use-case/workflow 추가
3. infrastructure adapter 연결
4. 테스트 작성
5. 로깅 적용 (`docs/rules/logging.md` 참고)

---

## 버그 수정 절차

- 재현 테스트 우선
- 최소 변경 원칙
- 에러 로그로 스택 트레이스 확인
