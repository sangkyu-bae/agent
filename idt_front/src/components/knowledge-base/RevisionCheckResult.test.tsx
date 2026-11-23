// document-revision §5.1·§5.4 — 사전 점검 결과 패널
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { RevisionCheckResponse } from '@/types/knowledgeBase';
import { initialDecision, type RevisionDecision } from './revisionDecision';
import RevisionCheckResult from './RevisionCheckResult';

const candidate = (id: string, name: string, version = 2) => ({
  document_id: id,
  filename: name,
  version_no: version,
  version_label: version > 1 ? '2025-03 개정' : null,
  filename_score: 0.92,
  content_score: 0.88,
  combined_score: 0.9,
  llm_verdict: 'same_document_revision' as const,
  llm_reason: '제1조(목적) 문구가 같고 시행일만 다르다',
});

const result = (over: Partial<RevisionCheckResponse> = {}): RevisionCheckResponse => ({
  check_id: 'chk',
  verdict: 'revision_candidate',
  duplicate_of: null,
  suggested_document_id: 'old',
  candidates: [candidate('old', '여신심사기준_2025.pdf'), candidate('alt', '여신심사기준_세칙.pdf', 1)],
  llm_status: 'ok',
  elapsed_ms: 100,
  ...over,
});

const Harness = ({ data }: { data: RevisionCheckResponse }) => {
  const [decision, setDecision] = useState<RevisionDecision>(initialDecision(data));
  return (
    <>
      <RevisionCheckResult result={data} decision={decision} onChange={setDecision} />
      <output data-testid="decision">{JSON.stringify(decision)}</output>
    </>
  );
};

const decisionOf = () => JSON.parse(screen.getByTestId('decision').textContent ?? '{}');

describe('RevisionCheckResult', () => {
  it('개정 후보: 제안 문서·근거·점수를 보여주고 기본 선택은 제안 문서 개정', () => {
    render(<Harness data={result()} />);
    expect(
      screen.getByText(/기존 「여신심사기준_2025\.pdf」 v2 · 2025-03 개정의 개정본으로 보입니다/),
    ).toBeInTheDocument();
    expect(screen.getByText(/제1조\(목적\) 문구가 같고/)).toBeInTheDocument();
    expect(screen.getByText(/파일명 92%/)).toBeInTheDocument();
    expect(screen.getByText(/본문 88%/)).toBeInTheDocument();
    expect(decisionOf()).toMatchObject({ mode: 'revision', targetId: 'old' });
    expect(screen.getByLabelText('버전 라벨')).toBeInTheDocument();
    expect(screen.getByLabelText('시행일')).toBeInTheDocument();
  });

  it('새 문서로 올리기를 고르면 라벨 입력이 사라진다', async () => {
    const user = userEvent.setup();
    render(<Harness data={result()} />);
    await user.click(screen.getByRole('radio', { name: /새 문서로 올리기/ }));
    expect(decisionOf().mode).toBe('new');
    expect(screen.queryByLabelText('버전 라벨')).not.toBeInTheDocument();
  });

  it('다른 후보를 대상으로 고를 수 있다', async () => {
    const user = userEvent.setup();
    render(<Harness data={result()} />);
    await user.selectOptions(screen.getByLabelText('대상 문서'), 'alt');
    expect(decisionOf().targetId).toBe('alt');
  });

  it('라벨·시행일 입력이 결정에 반영된다', async () => {
    const user = userEvent.setup();
    render(<Harness data={result()} />);
    await user.type(screen.getByLabelText('버전 라벨'), '2026-11 개정');
    expect(decisionOf().versionLabel).toBe('2026-11 개정');
  });

  it('LLM 판정 실패 시 점수 기준 제안임을 알린다', () => {
    render(<Harness data={result({ llm_status: 'failed' })} />);
    expect(screen.getByText(/자동 판정을 하지 못해/)).toBeInTheDocument();
  });

  it('신규 판정: 안내 + 후보가 있으면 개정 지정 선택지, 기본값은 새 문서', () => {
    render(
      <Harness
        data={result({ verdict: 'new', suggested_document_id: null })}
      />,
    );
    expect(screen.getByText(/일치하는 개정 대상이 없습니다/)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /개정본으로 올리기/ })).toBeInTheDocument();
    expect(decisionOf().mode).toBe('new');
  });

  it('신규 판정 + 후보 없음: 선택지 없이 안내만', () => {
    render(
      <Harness
        data={result({ verdict: 'new', suggested_document_id: null, candidates: [] })}
      />,
    );
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('완전 동일 파일: 기존 문서를 안내하고 선택지를 숨긴다', () => {
    render(
      <Harness
        data={result({
          verdict: 'duplicate',
          suggested_document_id: null,
          candidates: [],
          duplicate_of: {
            document_id: 'old', filename: '규정.pdf', lineage_id: 'old',
            version_no: 2, version_label: null, effective_date: null,
            revision_status: 'active', sync_state: 'synced', superseded_by: null,
            superseded_at: null, revised_by: null, created_at: '2026-03-02T09:00:00',
          },
        })}
      />,
    );
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('이미 같은 파일이 있습니다');
    expect(alert).toHaveTextContent('규정.pdf');
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('이전 버전과 같은 파일이면 되돌리기를 안내한다', () => {
    render(
      <Harness
        data={result({
          verdict: 'duplicate',
          candidates: [],
          duplicate_of: {
            document_id: 'v1', filename: '규정.pdf', lineage_id: 'v1',
            version_no: 1, version_label: null, effective_date: null,
            revision_status: 'superseded', sync_state: 'synced', superseded_by: 'v2',
            superseded_at: null, revised_by: null, created_at: null,
          },
        })}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/이전 버전과 같은 파일/);
  });
});
