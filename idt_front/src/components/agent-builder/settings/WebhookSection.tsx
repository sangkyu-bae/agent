import { useEffect, useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { API_BASE_URL } from '@/constants/api';
import {
  extractWebhookError,
  useAgentWebhook,
  useDeleteWebhook,
  useEnableWebhook,
  useRotateWebhookSecret,
  useUpdateWebhook,
  useWebhookDeliveries,
} from '@/hooks/useAgentWebhook';
import type { WebhookSecretIssue } from '@/types/agentWebhook';

interface WebhookSectionProps {
  /** create 모드는 null — 저장 후(edit)에만 설정 가능 (Design D9) */
  agentId: string | null;
}

const INFO_TEXT =
  '외부 시스템(n8n, Dify, 그룹웨어 등)이 아래 URL로 POST하면 이 에이전트가 실행됩니다. ' +
  '요청에는 X-Webhook-Timestamp와 X-Webhook-Signature(HMAC-SHA256) 헤더 서명이 필요합니다.';

/**
 * 설정 탭 Webhook 섹션 (agent-webhook M1).
 *
 * 웹훅 설정은 서버 상태(TanStack Query)로 탭 내 즉시 반영된다 —
 * StudioHeader 폼 저장(maxIterations 등 폼 상태)과 관리 주체가 다름에 주의.
 * 발급/재발급 시크릿 평문은 응답 1회만 로컬 상태(모달)로 노출하고 캐시에 넣지 않는다.
 */
const WebhookSection = ({ agentId }: WebhookSectionProps) => {
  const { data: config, isLoading } = useAgentWebhook(agentId);
  const enable = useEnableWebhook();
  const rotate = useRotateWebhookSecret();
  const update = useUpdateWebhook();
  const remove = useDeleteWebhook();

  const [issued, setIssued] = useState<WebhookSecretIssue | null>(null);
  const [error, setError] = useState<string | null>(null);
  // M2 outbound — URL 입력은 로컬 draft + 저장 확정 (매 키입력 PATCH 방지)
  const [outboundDraft, setOutboundDraft] = useState('');
  const [deliveriesOpen, setDeliveriesOpen] = useState(false);
  const { data: deliveries } = useWebhookDeliveries(agentId, {
    enabled: deliveriesOpen && config?.configured === true,
  });

  // 서버 값 변경(등록/해제/재조회) 시 draft 동기화
  useEffect(() => {
    setOutboundDraft(config?.outbound_url ?? '');
  }, [config?.outbound_url]);

  const mutationOpts = {
    onSuccess: (res: WebhookSecretIssue) => {
      setError(null);
      setIssued(res);
    },
    onError: (e: unknown) => setError(extractWebhookError(e)),
  };

  const copyText = (text: string) => {
    void navigator.clipboard.writeText(text);
  };

  const inboundUrl = config?.inbound_path
    ? `${API_BASE_URL}${config.inbound_path}`
    : null;

  const renderBody = () => {
    if (!agentId) {
      return (
        <p className="mt-3 text-[12.5px] text-zinc-400">
          에이전트를 먼저 저장하면 웹훅을 설정할 수 있습니다.
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
            isPending={enable.isPending}
            pendingText="발급 중…"
            onClick={() => enable.mutate({ agentId }, mutationOpts)}
            className="rounded-lg bg-violet-600 px-3 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-violet-700"
          >
            웹훅 활성화
          </LoadingButton>
        </div>
      );
    }
    return (
      <div className="mt-3 space-y-3">
        {/* 수신 URL */}
        <div>
          <span className="text-[12px] font-semibold text-zinc-500">수신 URL</span>
          <div className="mt-1 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] text-zinc-700">
              {inboundUrl}
            </code>
            <button
              type="button"
              aria-label="수신 URL 복사"
              onClick={() => inboundUrl && copyText(inboundUrl)}
              className="rounded-lg px-2 py-1.5 text-[12px] text-zinc-500 transition-colors hover:bg-zinc-100"
            >
              복사
            </button>
          </div>
        </div>

        {/* 시크릿 + 재발급 */}
        <div className="flex items-center justify-between">
          <div>
            <span className="text-[12px] font-semibold text-zinc-500">시크릿</span>
            <p className="mt-0.5 font-mono text-[12.5px] text-zinc-700">
              whsec_····{config.secret_hint}
            </p>
          </div>
          <LoadingButton
            isPending={rotate.isPending}
            pendingText="재발급 중…"
            onClick={() => {
              if (
                window.confirm(
                  '키를 재발급하면 기존 키는 즉시 사용할 수 없게 됩니다. 계속할까요?',
                )
              ) {
                rotate.mutate({ agentId }, mutationOpts);
              }
            }}
            className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
          >
            키 재발급
          </LoadingButton>
        </div>

        {/* 활성 토글 */}
        <div className="flex items-center justify-between">
          <span className="text-[13px] font-semibold text-zinc-700">Webhook 활성화</span>
          <button
            type="button"
            role="switch"
            aria-checked={config.enabled === true}
            aria-label="Webhook 토글"
            disabled={update.isPending}
            onClick={() =>
              update.mutate(
                { agentId, data: { enabled: !(config.enabled === true) } },
                { onError: (e) => setError(extractWebhookError(e)) },
              )
            }
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

        {/* ── 결과 발송 (Outbound, M2) ── */}
        <div className="border-t border-zinc-200 pt-3">
          <p className="text-[13px] font-semibold text-zinc-700">결과 발송 (Outbound)</p>
          <p className="mt-1 text-[12px] leading-[1.6] text-zinc-500">
            ⓘ 스케줄·웹훅 실행 결과를 아래 URL로 자동 발송합니다. 발송 요청에도 동일한
            서명 헤더가 포함됩니다.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input
              type="url"
              aria-label="outbound URL"
              placeholder="https://example.com/receive"
              value={outboundDraft}
              onChange={(e) => setOutboundDraft(e.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-[12.5px] text-zinc-900 outline-none transition-colors focus:border-violet-400"
            />
            <LoadingButton
              isPending={update.isPending}
              pendingText="저장 중…"
              disabled={!outboundDraft.trim()}
              onClick={() =>
                update.mutate(
                  { agentId, data: { outbound_url: outboundDraft.trim() } },
                  {
                    onSuccess: () => setError(null),
                    onError: (e) => setError(extractWebhookError(e)),
                  },
                )
              }
              className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
            >
              URL 저장
            </LoadingButton>
            {config.outbound_url && (
              <button
                type="button"
                onClick={() =>
                  update.mutate(
                    { agentId, data: { outbound_url: null } },
                    { onError: (e) => setError(extractWebhookError(e)) },
                  )
                }
                className="rounded-lg px-2 py-1.5 text-[12px] text-zinc-400 transition-colors hover:bg-zinc-100 hover:text-zinc-700"
              >
                해제
              </button>
            )}
          </div>
          <div className="mt-2.5 flex items-center justify-between">
            <span className="text-[13px] font-semibold text-zinc-700">결과 발송 활성화</span>
            <button
              type="button"
              role="switch"
              aria-checked={config.outbound_enabled === true}
              aria-label="Outbound 토글"
              disabled={update.isPending}
              onClick={() =>
                update.mutate(
                  {
                    agentId,
                    data: { outbound_enabled: !(config.outbound_enabled === true) },
                  },
                  { onError: (e) => setError(extractWebhookError(e)) },
                )
              }
              className={`relative h-5 w-9 rounded-full transition-colors ${
                config.outbound_enabled ? 'bg-violet-600' : 'bg-zinc-200'
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all ${
                  config.outbound_enabled ? 'left-[18px]' : 'left-0.5'
                }`}
              />
            </button>
          </div>
          <button
            type="button"
            aria-expanded={deliveriesOpen}
            onClick={() => setDeliveriesOpen((v) => !v)}
            className="mt-2.5 text-[12px] font-semibold text-zinc-500 transition-colors hover:text-zinc-700"
          >
            {deliveriesOpen ? '▾' : '▸'} 최근 전송 이력
          </button>
          {deliveriesOpen && (
            <ul className="mt-1.5 space-y-1">
              {(deliveries ?? []).length === 0 && (
                <li className="text-[12px] text-zinc-400">아직 발송 이력이 없습니다</li>
              )}
              {(deliveries ?? []).map((d) => (
                <li key={d.id} className="rounded-lg bg-white px-2.5 py-1.5 text-[12px]">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-[11px] font-semibold ${
                        d.success
                          ? 'bg-emerald-50 text-emerald-600'
                          : 'bg-red-50 text-red-500'
                      }`}
                    >
                      {d.success ? '성공' : '실패'}
                    </span>
                    <span className="text-zinc-600">
                      {d.trigger_source === 'schedule' ? '스케줄' : '웹훅'}
                    </span>
                    <span className="text-zinc-400">
                      {d.status_code ?? '연결 실패'} · {d.attempts}회
                    </span>
                    <span className="ml-auto text-zinc-400">
                      {new Date(d.created_at).toLocaleString()}
                    </span>
                  </div>
                  {!d.success && d.error && (
                    <p className="mt-1 truncate text-[11.5px] text-red-400">{d.error}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 삭제 */}
        <div className="flex items-center justify-between border-t border-zinc-200 pt-3">
          <p className="text-[12px] text-amber-600">
            ⚠ 이 에이전트는 소유자(나)의 권한으로 실행됩니다.
          </p>
          <LoadingButton
            isPending={remove.isPending}
            pendingText="삭제 중…"
            onClick={() => {
              if (
                window.confirm(
                  '웹훅을 삭제하면 키가 폐기되고 외부 호출이 즉시 차단됩니다. 계속할까요?',
                )
              ) {
                remove.mutate(
                  { agentId },
                  { onError: (e) => setError(extractWebhookError(e)) },
                );
              }
            }}
            className="rounded-lg px-2.5 py-1.5 text-[12px] font-semibold text-red-500 transition-colors hover:bg-red-50"
          >
            웹훅 삭제
          </LoadingButton>
        </div>
      </div>
    );
  };

  return (
    <section className="mb-6">
      <h3 className="mb-2 text-[15px] font-semibold text-zinc-900">Webhook</h3>
      <div className="rounded-xl bg-zinc-50 p-4">
        <p className="text-[12.5px] leading-[1.6] text-zinc-500">ⓘ {INFO_TEXT}</p>
        {error && (
          <p role="alert" className="mt-2 text-[12px] text-red-500">
            {error}
          </p>
        )}
        {renderBody()}
      </div>

      {/* 시크릿 1회 노출 모달 (발급/재발급 직후) */}
      {issued && (
        <div
          role="dialog"
          aria-label="웹훅 시크릿"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
        >
          <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
            <h4 className="text-[15px] font-semibold text-zinc-900">
              웹훅 시크릿이 발급되었습니다
            </h4>
            <p className="mt-1.5 text-[12.5px] leading-[1.6] text-zinc-500">
              이 키는 지금 한 번만 표시됩니다. 안전한 곳에 보관하세요 — 분실 시
              재발급해야 합니다.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded-lg border border-zinc-200 bg-zinc-50 px-2.5 py-2 text-[12px] text-zinc-800">
                {issued.secret}
              </code>
              <button
                type="button"
                aria-label="시크릿 복사"
                onClick={() => copyText(issued.secret)}
                className="rounded-lg border border-zinc-300 px-2.5 py-1.5 text-[12px] font-semibold text-zinc-600 transition-colors hover:bg-zinc-100"
              >
                복사
              </button>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                type="button"
                onClick={() => setIssued(null)}
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

export default WebhookSection;
