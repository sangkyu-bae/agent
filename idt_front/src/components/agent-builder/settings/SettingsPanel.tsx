import { MAX_ITERATIONS, TOKEN_LIMIT } from '@/constants/agentSettings';
import LimitNumberField from './LimitNumberField';
import WebhookSection from './WebhookSection';

interface SettingsPanelProps {
  /** 웹훅 섹션용 — create 모드는 null (저장 후 설정 가능, agent-webhook D9) */
  agentId: string | null;
  /** 현재 반복 한도 (form.maxIterations — 단일 진실원) */
  maxIterations: number;
  /** 확정된(clamp 완료) 값만 올라온다 — 상위는 검증 불필요 (Design D2) */
  onMaxIterationsChange: (value: number) => void;
  /** agent-token-limit D12: 현재 토큰 예산 (form.tokenLimit — 단일 진실원) */
  tokenLimit: number;
  /** clamp 완료 값만 올라온다 */
  onTokenLimitChange: (value: number) => void;
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
 * 입력·clamp 규칙은 LimitNumberField 가 담당한다 (Design D2·D3, agent-token-limit D12
 * 에서 토큰 예산과 공용화). Token Limit 섹션은 같은 필드로 8000~500000 clamp.
 * Webhook은 실기능(WebhookSection — 서버 상태, 탭 내 즉시 반영),
 * MCP/Telegram은 disabled 토글 스텁 유지.
 */
const SettingsPanel = ({
  agentId,
  maxIterations,
  onMaxIterationsChange,
  tokenLimit,
  onTokenLimitChange,
}: SettingsPanelProps) => {
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
          <LimitNumberField
            id="max-iterations-input"
            label="최대 반복 횟수"
            value={maxIterations}
            min={MAX_ITERATIONS.MIN}
            max={MAX_ITERATIONS.MAX}
            defaultValue={MAX_ITERATIONS.DEFAULT}
            onChange={onMaxIterationsChange}
            hint="복잡한 작업은 더 높은 값이 필요할 수 있습니다."
          />
        </div>
      </section>

      {/* ── Token Limit (agent-token-limit D12) ── */}
      <section className="mb-6">
        <h3 className="mb-2 flex items-center gap-2 text-[15px] font-semibold text-zinc-900">
          <svg className="h-4 w-4 text-zinc-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 6.75A2.25 2.25 0 0 1 5.25 4.5h13.5A2.25 2.25 0 0 1 21 6.75v10.5A2.25 2.25 0 0 1 18.75 19.5H5.25A2.25 2.25 0 0 1 3 17.25V6.75Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 9.75h18M7.5 14.25h3" />
          </svg>
          Token Limit
        </h3>
        <div className="rounded-xl bg-zinc-50 p-4">
          <p className="text-[12.5px] leading-[1.6] text-zinc-500">
            ⓘ 한 번의 실행에서 워커 산출물에 쓸 수 있는 토큰 예산입니다. 긴 수집 결과가 많은
            작업이면 값을 올리세요. 산출물 글자 수 기준의 추정치이며 실제 모델 토큰과 다를 수 있습니다.
          </p>
          <LimitNumberField
            id="token-limit-input"
            label="토큰 예산"
            value={tokenLimit}
            min={TOKEN_LIMIT.MIN}
            max={TOKEN_LIMIT.MAX}
            defaultValue={TOKEN_LIMIT.DEFAULT}
            onChange={onTokenLimitChange}
          />
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
