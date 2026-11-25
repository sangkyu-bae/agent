import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { API_BASE_URL } from '@/constants/api';
import {
  alertReceiverErrorMessage,
  useAlertReceipts,
  useAlertReceiver,
  useRotateAlertToken,
  useUpsertAlertReceiver,
} from '@/hooks/useAlertReceiver';
import { SCHEDULE_SKIP_REASON_LABEL } from '@/types/agentSchedule';
import {
  ALERT_INSTRUCTION_PREFIX_MAX,
  ALERT_RECEIPT_RESULT_LABEL,
  type UpsertAlertReceiverRequest,
} from '@/types/alertReceiver';

interface AlertReceiverSectionProps {
  /** create 모드는 null — 저장 후(edit)에만 설정 가능 */
  agentId: string | null;
}

const INFO_TEXT =
  'Grafana·Prometheus 같은 모니터링 시스템이 알림을 보내면 이 에이전트가 실행됩니다. ' +
  '알림 형식은 Alertmanager 웹훅이고, Authorization: Bearer <토큰> 헤더로 인증합니다. ' +
  '받으면 바로 응답하고 실행은 백그라운드 작업으로 진행됩니다.';

/**
 * 설정 탭 "알림 수신" (firewall-agent design §5.2).
 * 토큰 평문은 생성·재발급 응답 1회만 로컬 상태(모달)로 보여 주고 캐시에 넣지 않는다.
 */
const AlertReceiverSection = ({ agentId }: AlertReceiverSectionProps) => {
  const { data: config, isLoading } = useAlertReceiver(agentId);
  const upsert = useUpsertAlertReceiver();
  const rotate = useRotateAlertToken();
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 편집 전에는 null — 서버 값을 그대로 보여 주고, 저장 성공 시 다시 null 로 돌린다
  // (useEffect 로 서버 값을 복사하지 않는다)
  const [prefixDraft, setPrefixDraft] = useState<string | null>(null);
  const prefixValue = prefixDraft ?? config?.instruction_prefix ?? '';
  const [receiptsOpen, setReceiptsOpen] = useState(false);
  const { data: receipts } = useAlertReceipts(agentId, {
    enabled: receiptsOpen && config?.configured === true,
  });

  const save = (data: UpsertAlertReceiverRequest) => {
    if (!agentId) return;
    upsert.mutate(
      { agentId, data },
      {
        onSuccess: (res) => {
          setError(null);
          if (data.instruction_prefix !== undefined) setPrefixDraft(null);
          if (res.token) setToken(res.token);
        },
        onError: (e) => setError(alertReceiverErrorMessage(e)),
      },
    );
  };

  const inboundUrl = config?.inbound_path ? `${API_BASE_URL}${config.inbound_path}` : null;

  const renderBody = () => {
    if (!agentId) {
      return (
        <p className="mt-3 text-[12.5px] text-zinc-400">
          에이전트를 먼저 저장하면 알림 수신을 설정할 수 있습니다.
        </p>
      );
    }
    if (isLoading || !config) {
      return <p className="mt-3 text-[12.5px] text-zinc-400">불러오는 중…</p>;
    }
    if (!config.configured) {
      return (
        <div className="mt-3">
          <LoadingButton
            isPending={upsert.isPending}
            pendingText="설정 중…"
            onClick={() => save({})}
            className="rounded-lg bg-violet-600 px-3 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-violet-700"
          >
            알림 수신 설정
          </LoadingButton>
        </div>
      );
    }
    return (
      <div className="mt-3 space-y-3">
        <div>
          <span className="text-[12px] font-semibold text-zinc-500">수신 URL</span>
          <div className="mt-1 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] text-zinc-700">
              {inboundUrl}
            </code>
            <button
              type="button"
              aria-label="알림 수신 URL 복사"
              onClick={() => inboundUrl && void navigator.clipboard.writeText(inboundUrl)}
              className="rounded-lg px-2 py-1.5 text-[12px] text-zinc-500 transition-colors hover:bg-zinc-100"
            >
              복사
            </button>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <div>
            <span className="text-[12px] font-semibold text-zinc-500">토큰</span>
            <p className="mt-0.5 font-mono text-[12.5px] text-zinc-700">····{config.token_hint}</p>
          </div>
          <LoadingButton
            isPending={rotate.isPending}
            pendingText="재발급 중…"
            onClick={() => {
              if (
                window.confirm(
                  '토큰을 재발급하면 기존 토큰은 바로 쓸 수 없습니다. 모니터링 쪽 설정도 바꿔야 합니다. 계속할까요?',
                )
              ) {
                rotate.mutate(
                  { agentId },
                  {
                    onSuccess: (res) => {
                      setError(null);
                      if (res.token) setToken(res.token);
                    },
                    onError: (e) => setError(alertReceiverErrorMessage(e)),
                  },
                );
              }
            }}
            className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
          >
            토큰 재발급
          </LoadingButton>
        </div>

        <div className="flex items-center justify-between">
          <span className="text-[13px] font-semibold text-zinc-700">알림 수신 활성화</span>
          <button
            type="button"
            role="switch"
            aria-checked={config.enabled === true}
            aria-label="알림 수신 토글"
            disabled={upsert.isPending}
            onClick={() => save({ enabled: !(config.enabled === true) })}
            className={`relative h-5 w-9 rounded-full transition-colors ${
              config.enabled ? 'bg-violet-600' : 'bg-zinc-200'
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all ${
                config.enabled ? 'left-[18px]' : 'left-0.5'
              }`}
            />
          </button>
        </div>

        <label className="flex cursor-pointer items-start gap-2.5 text-[13px] text-zinc-700">
          <input
            type="checkbox"
            checked={config.skip_when_busy === true}
            disabled={upsert.isPending}
            onChange={(e) => save({ skip_when_busy: e.target.checked })}
            className="mt-0.5 h-4 w-4 rounded border-zinc-300 accent-violet-600"
          />
          <span>
            이전 실행이 진행 중이거나 승인 대기 중이면 건너뛰기
            <span className="mt-0.5 block text-[12px] text-zinc-400">
              같은 요청이 승인함에 쌓이지 않게 합니다.
            </span>
          </span>
        </label>

        <div>
          <span className="text-[12px] font-semibold text-zinc-500">
            지침 앞머리 (알림 내용 앞에 붙는 문장)
          </span>
          <div className="mt-1 flex items-start gap-2">
            <textarea
              aria-label="지침 앞머리"
              rows={2}
              maxLength={ALERT_INSTRUCTION_PREFIX_MAX}
              value={prefixValue}
              onChange={(e) => setPrefixDraft(e.target.value)}
              placeholder="예: 아래 탐지 알림을 정책대로 판단하라."
              className="min-w-0 flex-1 resize-none rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-[12.5px] text-zinc-900 outline-none transition-colors focus:border-violet-400"
            />
            <LoadingButton
              isPending={upsert.isPending}
              pendingText="저장 중…"
              disabled={prefixValue.trim() === (config.instruction_prefix ?? '')}
              onClick={() => save({ instruction_prefix: prefixValue.trim() })}
              className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
            >
              앞머리 저장
            </LoadingButton>
          </div>
        </div>

        <button
          type="button"
          aria-expanded={receiptsOpen}
          onClick={() => setReceiptsOpen((v) => !v)}
          className="text-[12px] font-semibold text-zinc-500 transition-colors hover:text-zinc-700"
        >
          {receiptsOpen ? '▾' : '▸'} 최근 수신
        </button>
        {receiptsOpen && (
          <ul className="space-y-1">
            {(receipts ?? []).length === 0 && (
              <li className="text-[12px] text-zinc-400">아직 받은 알림이 없습니다</li>
            )}
            {(receipts ?? []).map((r) => (
              <li
                key={r.id}
                className="flex items-center gap-2 rounded-lg bg-white px-2.5 py-1.5 text-[12px]"
              >
                <span className="rounded-full bg-zinc-100 px-1.5 py-0.5 text-[11px] font-semibold text-zinc-600">
                  {ALERT_RECEIPT_RESULT_LABEL[r.result] ?? r.result}
                </span>
                <span className="text-zinc-500">
                  발화 {r.firing_count}건
                  {r.skip_reason &&
                    ` · ${SCHEDULE_SKIP_REASON_LABEL[r.skip_reason] ?? r.skip_reason}`}
                </span>
                <span className="ml-auto text-zinc-400">
                  {new Date(r.received_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  return (
    <section className="mb-6">
      <h3 className="mb-2 text-[15px] font-semibold text-zinc-900">알림 수신</h3>
      <div className="rounded-xl bg-zinc-50 p-4">
        <p className="text-[12.5px] leading-[1.6] text-zinc-500">ⓘ {INFO_TEXT}</p>
        {error && (
          <p role="alert" className="mt-2 text-[12px] text-red-500">
            {error}
          </p>
        )}
        {renderBody()}
      </div>

      {token && (
        <div
          role="dialog"
          aria-label="알림 수신 토큰"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        >
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h4 className="text-[15px] font-semibold text-zinc-900">알림 수신 토큰</h4>
            <p className="mt-1.5 text-[12.5px] leading-[1.6] text-zinc-500">
              이 토큰은 지금 한 번만 표시됩니다. 모니터링 시스템의 연락처(Contact point)에
              Bearer 토큰으로 넣으세요. 분실하면 재발급해야 합니다.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-2 text-[12px] text-zinc-800">
                {token}
              </code>
              <button
                type="button"
                aria-label="토큰 복사"
                onClick={() => void navigator.clipboard.writeText(token)}
                className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
              >
                복사
              </button>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setToken(null)}
                className="rounded-lg bg-zinc-900 px-3.5 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-zinc-700"
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

export default AlertReceiverSection;
