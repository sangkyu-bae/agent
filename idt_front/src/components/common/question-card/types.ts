// Design Ref: question-card §3 — 도메인 비의존 제네릭 질문 모델.
// agentComposer 등 도메인 타입을 import하지 않는다 (Plan FR-10).

/** 질문 1건 — 카드 1장에 대응 */
export interface FlowQuestion {
  id: string;
  /** 카드 헤더에 표시되는 질문 텍스트 */
  title: string;
  /** 선택지 (빈 배열 허용 — 직접 입력만 있는 질문) */
  options: string[];
  /** true면 마지막 행에 직접 입력 라디오 추가 */
  allowFreeText: boolean;
  /** 직접 입력 행 레이블 (기본: '직접 입력 (원하는 내용을 자유롭게 작성)') */
  freeTextLabel?: string;
}

/** 답변 1건 — value===''는 무응답(건너뛰기) */
export interface FlowAnswer {
  id: string;
  value: string;
}
