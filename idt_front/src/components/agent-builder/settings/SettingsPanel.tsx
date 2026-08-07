import { useEffect, useState } from 'react';
import { MAX_ITERATIONS } from '@/constants/agentSettings';
import WebhookSection from './WebhookSection';

interface SettingsPanelProps {
  /** 웹훅 섹션용 — create 모드는 null (저장 후 설정 가능, agent-webhook D9) */
  agentId: string | null;
  /** 현재 반복 한도 (form.maxIterations — 단일 진실원) */
  maxIterations: number;
  /** 확정된(clamp 완료) 값만 올라온다 — 상위는 검증 불필요 (Design D2) */
  onMaxIterationsChange: (value: number) => void;
}

/** 연동 스텁 섹션 정의 — 실기능은 각각 별도 PDCA로 후속 (Design D8) */
const STUB_SECTIONS = [
  {
    id: 'mcp',
    title: 'MCP 서버',
    info: 'MCP 서버를 활성화하면 Claude Desktop, Cursor 등 MCP 호환 클라이언트에서 이 에이전트를 사용할 수 있습니다.',
    toggleLabel: 'MCP 서버 활성화',
    status: null,
  },
  {
    id: 'telegram',
    title: 'Telegram 연동',
    info: 'Telegram Bot을 연결하여 채팅으로 Agent와 대화할 수 있습니다.',
    toggleLabel: '비활성화됨',
    status: '연결되지 않음',
  },
] as const;

/**
 * 설정 탭 패널 (agent-settings-tab → agent-webhook).
 *
 * Recursion Limit — form.maxIterations에 바인딩되어 StudioHeader
 * 저장 버튼으로 create/update의 max_iterations에 실린다 (탭 내 저장 없음).
 * 입력은 로컬 문자열로 자유 타이핑을 허용하고 blur/Enter 확정 시점에
 * 10~1000으로 clamp한다 — 빈 값·비숫자는 기존 값 복원 (Design D2·D3).
 * Webhook은 실기능(WebhookSection — 서버 상태, 탭 내 즉시 반영),
 * MCP/Telegram은 disabled 토글 스텁 유지.
 */
const SettingsPanel = ({ agentId, maxIterations, onMaxIterationsChange }: SettingsPanelProps) => {
  const [draft, setDraft] = useState(String(maxIterations));

  // 상위 값 변경(edit 프라임·복원 버튼) 시 로컬 입력 동기화
  useEffect(() => {
    setDraft(String(maxIterations));
  }, [maxIterations]);

  const commitDraft = () => {
    const parsed = Number.parseInt(draft, 10);
    if (Number.isNaN(parsed)) {
      setDraft(String(maxIterations));
      return;
    }
    const clamped = Math.min(MAX_ITERATIONS.MAX, Math.max(MAX_ITERATIONS.MIN, parsed));
    setDraft(String(clamped));
    onMaxIterationsChange(clamped);
  };

  return (
    <div style={{ height: '100%', overflowY: 'auto' }} className="px-4 py-4">
      <p className="mb-4 text-[12px] text-zinc-400">에이전트 실행 설정을 관리합니다</p>

      {/* ── Recursion Limit (실기능) ── */}
      <section className="mb-6">
        <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
          <svg className="h-4 w-4 text-zinc-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.992a7.723 7.723 0 0 1 0-.255c.007-.378-.138-.75-.43-.991l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
          </svg>
          Recursion Limit
        </h3>
        <div className="rounded-xl bg-zinc-50 p-4">
          <p className="text-[12.5px] leading-[1.6] text-zinc-500">
            ⓘ 에이전트가 반복적으로 실행될 수 있는 최대 횟수입니다. 복잡한 작업이나 긴 대화에서
            무한 루프를 방지합니다.
          </p>
          <div className="mt-3">
            <label htmlFor="max-iterations-input" className="text-[13px] font-semibold text-zinc-700">
              최대 반복 횟수
            </label>
            <div className="mt-1.5 flex items-center gap-2">
              <input
                id="max-iterations-input"
                type="number"
                value={draft}
                min={MAX_ITERATIONS.MIN}
                max={MAX_ITERATIONS.MAX}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commitDraft}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitDraft();
                }}
                className="w-24 rounded-lg border border-zinc-300 bg-white px-3 py-1.5 text-[13px] text-zinc-900 outline-none transition-colors focus:border-violet-400"
              />
              <button
                type="button"
                aria-label="기본값으로 복원"
                title="기본값으로 복원"
                onClick={() => onMaxIterationsChange(MAX_ITERATIONS.DEFAULT)}
                className="rounded-lg p-1.5 text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 15 3 9m0 0 6-6M3 9h12a6 6 0 0 1 0 12h-3" />
                </svg>
              </button>
              <span className="text-[12px] text-zinc-400">
                (범위: {MAX_ITERATIONS.MIN} - {MAX_ITERATIONS.MAX})
              </span>
            </div>
            <p className="mt-2 text-[12px] text-zinc-400">
              기본값: {MAX_ITERATIONS.DEFAULT}. 복잡한 작업은 더 높은 값이 필요할 수 있습니다.
            </p>
          </div>
        </div>
      </section>

      {/* ── Webhook (실기능 — agent-webhook M1) ── */}
      <WebhookSection agentId={agentId} />

      {/* ── 연동 스텁 2종 (토글 disabled + 준비중) ── */}
      {STUB_SECTIONS.map((s) => (
        <section key={s.id} className="mb-6">
          <h3 className="mb-2 text-[15px] font-semibold text-zinc-900">{s.title}</h3>
          <div className="rounded-xl bg-zinc-50 p-4">
            <p className="text-[12.5px] leading-[1.6] text-zinc-500">ⓘ {s.info}</p>
            {s.status && (
              <p className="mt-2 flex items-center gap-1 text-[12px] text-zinc-400">
                <span aria-hidden="true">⊗</span>
                <span>{s.status}</span>
              </p>
            )}
            <div className="mt-3 flex items-center justify-between">
              <span className="text-[13px] font-semibold text-zinc-700">{s.toggleLabel}</span>
              <button
                type="button"
                role="switch"
                aria-checked={false}
                aria-label={`${s.title} 토글`}
                disabled
                title="준비중"
                className="relative h-5 w-9 cursor-not-allowed rounded-full bg-zinc-200 opacity-60"
              >
                <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow-sm" />
              </button>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
};

export default SettingsPanel;
