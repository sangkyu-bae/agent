import type { ReactNode } from 'react';

interface QuestionCardProps {
  /** 카드 헤더에 표시되는 질문 텍스트 */
  title: string;
  /** 잠금 상태 — footer 대신 답변 완료 배지를 표시하고 시각적으로 감쇠 */
  locked?: boolean;
  /** 좁은 컨테이너(채팅 폭)용 축소 variant */
  compact?: boolean;
  /** 옵션 행 목록 슬롯 */
  children: ReactNode;
  /** 제출/건너뛰기 행 슬롯 — 없으면 푸터 미렌더 */
  footer?: ReactNode;
}

/**
 * Design Ref: question-card §5.1/§5.2 — 카드 셸 (헤더/옵션 슬롯/푸터 슬롯 3단 구조).
 * 상태를 갖지 않는다 — 조합 단위로 단독 사용 가능.
 */
const QuestionCard = ({
  title,
  locked = false,
  compact = false,
  children,
  footer,
}: QuestionCardProps) => (
  <div
    className={`border border-zinc-200 bg-violet-50/30 ${
      compact ? 'rounded-xl' : 'rounded-2xl'
    } ${locked ? 'opacity-70' : ''}`}
  >
    <div
      className={`flex items-center gap-2.5 border-b border-zinc-200/70 ${
        compact ? 'px-4 py-3' : 'px-5 py-4'
      }`}
    >
      <svg
        className="h-5 w-5 shrink-0 text-violet-300"
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
      >
        <path d="M12 3C6.98 3 3 6.36 3 10.5c0 2.32 1.27 4.39 3.26 5.76-.1.82-.42 2.03-1.32 3.06a.42.42 0 0 0 .36.68c2.02-.1 3.55-.96 4.5-1.72.72.15 1.46.22 2.2.22 5.02 0 9-3.36 9-7.5S17.02 3 12 3Z" />
      </svg>
      <p
        className={`font-semibold text-zinc-900 ${
          compact ? 'text-[13.5px]' : 'text-[15px]'
        }`}
      >
        {title}
      </p>
    </div>

    <div className={compact ? 'space-y-2 px-4 py-3' : 'space-y-2.5 px-5 py-4'}>
      {children}
    </div>

    {locked ? (
      <div
        className={`flex justify-end border-t border-zinc-200/70 ${
          compact ? 'px-4 py-2.5' : 'px-5 py-3.5'
        }`}
      >
        <span className="text-[12.5px] font-medium text-violet-500">✓ 답변 완료</span>
      </div>
    ) : footer ? (
      <div
        className={`flex items-center justify-between border-t border-zinc-200/70 ${
          compact ? 'px-4 py-2.5' : 'px-5 py-3.5'
        }`}
      >
        {footer}
      </div>
    ) : null}
  </div>
);

export default QuestionCard;
