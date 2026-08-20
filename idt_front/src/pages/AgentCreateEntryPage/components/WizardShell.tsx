import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

interface WizardShellProps {
  /** centered: 첫 화면(세로 중앙) / chat: 트랜스크립트 + 하단 고정 입력창 */
  mode: 'centered' | 'chat';
  /** chat 모드 하단 고정 슬롯 — 스크롤 영역의 형제라 겹침이 구조적으로 불가하다. */
  composer?: ReactNode;
  /** 트랜스크립트 항목 수 등의 파생값 — 바뀔 때 하단 근처면 자동 스크롤. */
  scrollKey?: string;
  children: ReactNode;
}

/** 이 거리(px) 이내면 "바닥을 보는 중"으로 판단해 자동 스크롤한다. */
const NEAR_BOTTOM_PX = 120;

/**
 * 위저드 2-모드 레이아웃 셸 (Design: wizard-chat-layout §5.3).
 *
 * FR-15 — `justify-center` 금지: flexbox 는 넘친 콘텐츠를 스크롤 원점 위로
 * 밀어내 도달 불가 영역을 만든다. centered 모드는 자식 `my-auto` 로 대체한다
 * (auto 마진은 overflow 시 0으로 붕괴 → 짧으면 중앙, 길면 일반 스크롤).
 */
const WizardShell = ({ mode, composer, scrollKey, children }: WizardShellProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  // 사용자가 위로 스크롤해 이전 카드를 읽는 중이면 끌어내리지 않는다.
  const nearBottomRef = useRef(true);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    nearBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
  };

  useEffect(() => {
    if (mode !== 'chat') return;
    const el = scrollRef.current;
    if (!el || !nearBottomRef.current) return;
    el.scrollTo?.({ top: el.scrollHeight, behavior: 'smooth' });
  }, [mode, scrollKey]);

  if (mode === 'centered') {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
        }}
      >
        <div style={{ flex: 1, overflowY: 'auto' }} className="bg-zinc-50/60">
          <div className="mx-auto flex min-h-full w-full max-w-[760px] flex-col px-6 py-16">
            <div className="my-auto space-y-8">{children}</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: 'auto' }}
        className="bg-zinc-50/60"
        data-testid="wizard-transcript"
      >
        <div className="mx-auto w-full max-w-[760px] space-y-6 px-6 py-8">
          {children}
        </div>
      </div>
      {composer && (
        <div className="shrink-0 border-t border-zinc-200 bg-white px-6 py-4">
          <div className="mx-auto w-full max-w-[760px]">{composer}</div>
        </div>
      )}
    </div>
  );
};

export default WizardShell;
