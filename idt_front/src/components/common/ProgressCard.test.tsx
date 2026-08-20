// progress-card: 카드 조합 — 헤더 타이틀·배열 렌더링·빈 상태·시맨틱 목록.
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ProgressCard, { type ProgressStep } from './ProgressCard';

// Design Ref: §8.3 — docs/img/card.png 재현 픽스처
const AUTO_BUILD_STEPS: ProgressStep[] = [
  { label: 'Phase 1: 프로젝트 초기화', status: 'completed' },
  { label: 'Phase 2: 사용자 의도 분석 에이전트가 의도 수집', status: 'in_progress' },
  { label: 'Phase 3: 도구 추천 에이전트가 도구 추천', status: 'pending' },
  { label: 'Phase 4: 미들웨어 추천 에이전트가 미들웨어 추천', status: 'pending' },
  { label: 'Phase 5: 프롬프트 작성 에이전트가 시스템 프롬프트 생성', status: 'pending' },
  { label: 'Phase 6: 에이전트 설정 저장', status: 'pending' },
  { label: 'Phase 7: 에이전트 빌드', status: 'pending' },
];

describe('ProgressCard', () => {
  it('T1: 기본 타이틀 "진행 상황"을 렌더링한다', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} />);
    expect(screen.getByText('진행 상황')).toBeInTheDocument();
  });

  it('T2: title prop이 기본 타이틀을 오버라이드한다', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} title="빌드 진행" />);
    expect(screen.getByText('빌드 진행')).toBeInTheDocument();
    expect(screen.queryByText('진행 상황')).not.toBeInTheDocument();
  });

  it('T3: steps 배열의 모든 단계를 순서대로 렌더링한다', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} />);
    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(7);
    expect(items[0]).toHaveTextContent('Phase 1: 프로젝트 초기화');
    expect(items[6]).toHaveTextContent('Phase 7: 에이전트 빌드');
  });

  it('T4: 상태 혼합 배열에서 각 상태의 배지가 동시에 표시된다', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} />);
    expect(screen.getByText('완료')).toBeInTheDocument();
    expect(screen.getByText('진행중')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem').filter((li) => li.textContent?.includes('대기중'))).toHaveLength(5);
  });

  it('T5: 빈 배열이면 빈 상태 문구를 표시하고 목록은 없다', () => {
    render(<ProgressCard steps={[]} />);
    expect(screen.getByText('표시할 단계가 없습니다')).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('T6: 목록은 시맨틱 list role을 가진다', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} />);
    expect(screen.getByRole('list')).toBeInTheDocument();
  });

  it('T7: error 상태 단계는 "실패" 배지를 렌더링한다', () => {
    render(
      <ProgressCard
        steps={[
          { label: 'Phase 1: 프로젝트 초기화', status: 'completed' },
          { label: 'Phase 2: 의도 수집', status: 'error' },
        ]}
      />,
    );
    expect(screen.getByText('실패')).toBeInTheDocument();
  });

  it('T8: 마지막 단계에는 커넥터가 없다 (커넥터 수 = 단계 수 - 1)', () => {
    render(<ProgressCard steps={AUTO_BUILD_STEPS} />);
    expect(screen.getAllByTestId('step-connector')).toHaveLength(6);
  });

  it('T9: className prop이 카드 루트에 병합된다', () => {
    const { container } = render(<ProgressCard steps={AUTO_BUILD_STEPS} className="mt-4" />);
    expect((container.firstChild as HTMLElement).className).toContain('mt-4');
  });
});
