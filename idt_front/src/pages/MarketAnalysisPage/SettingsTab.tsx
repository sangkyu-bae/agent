// stock-analysis-agents §9.4 설정 — manage 만 편집, view 는 읽기(입력 비활성, L2 #6).
// 자동 분석 스위치는 끌 때만 확인창(방화벽 선례, L2 #5). 켜려면 KIS 서버·실행 사용자가 필요(서버가 422).
import { useState, type ReactNode } from 'react';
import Button from '@/components/ui/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useMcpServers } from '@/hooks/useMcpServers';
import { useMarketSettings, useSaveSettings, useSetEnabled } from '@/hooks/useMarketAnalysis';
import {
  RANKING_KIND_LABELS,
  RANKING_KINDS,
  REGIME_LABELS,
  REGIMES,
  SIGNAL_RULE_LABELS,
  SIGNAL_RULES,
  type MarketAnalysisSettings,
} from '@/types/marketAnalysis';
import { marketAnalysisErrorMessage, settingFieldErrors, withoutSwitch } from '@/utils/marketAnalysis';
import RoleAgentTable from './RoleAgentTable';
import { Card, ErrorBox, Loading } from './parts';

interface SettingsTabProps {
  canManage: boolean;
}

const SERVER_FIELDS = [
  { key: 'kis_server_id', label: 'KIS 서버 (필수)' },
  { key: 'dart_server_id', label: 'DART 서버' },
  { key: 'perplexity_server_id', label: 'Perplexity 서버' },
] as const;

const Field = ({ label, error, children }: { label: string; error?: string; children: ReactNode }) => (
  <label className="block text-sm">
    <span className="mb-1 block text-xs text-fg-muted">{label}</span>
    {children}
    {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
  </label>
);

const inputClass =
  'h-8 w-full rounded-md border border-border bg-surface px-2 text-sm text-fg disabled:bg-surface-muted';

const splitList = (text: string): string[] =>
  text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

const SwitchRow = ({ settings, canManage }: { settings: MarketAnalysisSettings; canManage: boolean }) => {
  const setEnabled = useSetEnabled();
  const [confirmOff, setConfirmOff] = useState(false);
  const toggle = () => {
    if (settings.enabled) setConfirmOff(true);
    else setEnabled.mutate(true);
  };
  return (
    <Card title="자동 분석">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-fg">{settings.enabled ? '켜짐' : '꺼짐'}</span>
        <Button
          size="sm"
          variant={settings.enabled ? 'secondary' : 'primary'}
          disabled={!canManage}
          isPending={setEnabled.isPending && !confirmOff}
          onClick={toggle}
        >
          {settings.enabled ? '자동 분석 끄기' : '자동 분석 켜기'}
        </Button>
        {setEnabled.isError && !confirmOff && (
          <p role="alert" className="text-sm text-danger">
            {Object.values(settingFieldErrors(setEnabled.error)).join(' ') ||
              marketAnalysisErrorMessage(setEnabled.error, '스위치를 바꾸지 못했습니다.')}
          </p>
        )}
      </div>
      <p className="mt-2 text-xs text-fg-subtle">
        꺼져 있으면 회차 시각이 와도 분석하지 않고 건너뜀으로만 기록합니다(에이전트 비용 0).
      </p>
      <ConfirmDialog
        isOpen={confirmOff}
        title="자동 분석 끄기"
        description="다음 회차부터 분석하지 않습니다. 실행 중인 회차는 끝까지 진행되고, 보유 종목의 목표가·손절가 청산도 멈춥니다."
        confirmLabel="끄기"
        variant="warning"
        isPending={setEnabled.isPending}
        error={
          setEnabled.isError
            ? marketAnalysisErrorMessage(setEnabled.error, '스위치를 바꾸지 못했습니다.')
            : null
        }
        onClose={() => setConfirmOff(false)}
        onConfirm={() => setEnabled.mutate(false, { onSuccess: () => setConfirmOff(false) })}
      />
    </Card>
  );
};

const SettingsForm = ({
  initial,
  canManage,
  save,
}: {
  initial: MarketAnalysisSettings;
  canManage: boolean;
  /** 부모가 들고 있는 mutation — 저장 뒤 다시 불러와 폼이 새로 그려져도 성공·오류 상태가 남는다 */
  save: ReturnType<typeof useSaveSettings>;
}) => {
  const [form, setForm] = useState<MarketAnalysisSettings>(initial);
  const [roundTimes, setRoundTimes] = useState(initial.round_times.join(', '));
  const [conditionSeqs, setConditionSeqs] = useState(initial.condition_seqs.join(', '));
  const servers = useMcpServers();
  const errors = settingFieldErrors(save.error);

  const set = <K extends keyof MarketAnalysisSettings>(key: K, value: MarketAnalysisSettings[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const toggleIn = (key: 'signal_rules' | 'ranking_kinds', value: string) =>
    setForm((f) => ({
      ...f,
      [key]: f[key].includes(value) ? f[key].filter((v) => v !== value) : [...f[key], value],
    }));
  const num = (key: keyof MarketAnalysisSettings) => ({
    type: 'number' as const,
    value: String(form[key] ?? ''),
    onChange: (e: { target: { value: string } }) =>
      set(key, Number(e.target.value) as never),
    className: inputClass,
  });

  const submit = () =>
    save.mutate(
      withoutSwitch({
        ...form,
        round_times: splitList(roundTimes),
        condition_seqs: splitList(conditionSeqs),
      }),
    );

  const serverItems = servers.data?.items ?? [];

  return (
    <fieldset disabled={!canManage} className="space-y-5">
      <legend className="sr-only">분석 설정</legend>
      <Card title="회차와 상한">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="회차 시각 (서울, 쉼표로 구분)" error={errors.round_times}>
            <input aria-label="회차 시각" value={roundTimes} onChange={(e) => setRoundTimes(e.target.value)} className={inputClass} />
          </Field>
          <Field label="회차당 분석 상한" error={errors.max_per_round}>
            <input aria-label="회차당 분석 상한" {...num('max_per_round')} />
          </Field>
          <Field label="하루 분석 상한" error={errors.max_per_day}>
            <input aria-label="하루 분석 상한" {...num('max_per_day')} />
          </Field>
          <Field label="동시 분석 종목" error={errors.max_concurrent_stocks}>
            <input aria-label="동시 분석 종목" {...num('max_concurrent_stocks')} />
          </Field>
          <Field label="동시 에이전트 실행" error={errors.max_concurrent_runs}>
            <input aria-label="동시 에이전트 실행" {...num('max_concurrent_runs')} />
          </Field>
        </div>
      </Card>

      <Card title="후보와 신호">
        <p className="mb-2 text-xs text-fg-muted">신호 규칙</p>
        <div className="mb-3 flex flex-wrap gap-3" role="group" aria-label="신호 규칙">
          {SIGNAL_RULES.map((r) => (
            <label key={r} className="inline-flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={form.signal_rules.includes(r)} onChange={() => toggleIn('signal_rules', r)} />
              {SIGNAL_RULE_LABELS[r]}
            </label>
          ))}
        </div>
        {errors.signal_rules && <p className="mb-2 text-xs text-danger">{errors.signal_rules}</p>}
        <p className="mb-2 text-xs text-fg-muted">순위 종류</p>
        <div className="mb-3 flex flex-wrap gap-3" role="group" aria-label="순위 종류">
          {RANKING_KINDS.map((k) => (
            <label key={k} className="inline-flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={form.ranking_kinds.includes(k)} onChange={() => toggleIn('ranking_kinds', k)} />
              {RANKING_KIND_LABELS[k]}
            </label>
          ))}
        </div>
        {errors.ranking_kinds && <p className="mb-2 text-xs text-danger">{errors.ranking_kinds}</p>}
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="순위 조회 개수" error={errors.ranking_limit}>
            <input aria-label="순위 조회 개수" {...num('ranking_limit')} />
          </Field>
          <Field label="조건검색 번호 (쉼표로 구분)">
            <input aria-label="조건검색 번호" value={conditionSeqs} onChange={(e) => setConditionSeqs(e.target.value)} className={inputClass} />
          </Field>
        </div>
      </Card>

      <Card title="진입 규칙 (서버가 다시 계산)">
        <p className="mb-2 text-xs text-fg-muted">체제별 최소 점수</p>
        <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-5">
          {REGIMES.map((r) => (
            <Field key={r} label={REGIME_LABELS[r]}>
              <input
                aria-label={`${REGIME_LABELS[r]} 최소 점수`}
                type="number"
                value={String(form.min_score_by_regime[r] ?? '')}
                onChange={(e) =>
                  set('min_score_by_regime', { ...form.min_score_by_regime, [r]: Number(e.target.value) })
                }
                className={inputClass}
              />
            </Field>
          ))}
        </div>
        {errors.min_score_by_regime && <p className="mb-2 text-xs text-danger">{errors.min_score_by_regime}</p>}
        <div className="grid gap-3 md:grid-cols-4">
          <Field label="최소 손익비" error={errors.min_rr}>
            <input aria-label="최소 손익비" step="0.1" {...num('min_rr')} />
          </Field>
          <Field label="최소 손절폭 (%)" error={errors.min_stop_pct}>
            <input aria-label="최소 손절폭" step="0.1" {...num('min_stop_pct')} />
          </Field>
          <Field label="최대 손절폭 (%)" error={errors.max_stop_pct}>
            <input aria-label="최대 손절폭" step="0.1" {...num('max_stop_pct')} />
          </Field>
          <Field label="슬롯 수" error={errors.slot_count}>
            <input aria-label="슬롯 수" {...num('slot_count')} />
          </Field>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.intraday_entry_allowed} onChange={(e) => set('intraday_entry_allowed', e.target.checked)} />
          장중(미확정 봉) 진입 허용
        </label>
      </Card>

      <Card title="매매 원칙">
        <div className="grid gap-3 md:grid-cols-3">
          <Field label="판단에 넣을 원칙 수" error={errors.max_principles}>
            <input aria-label="판단에 넣을 원칙 수" {...num('max_principles')} />
          </Field>
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.principle_auto_activate} onChange={(e) => set('principle_auto_activate', e.target.checked)} />
          새 원칙 후보를 바로 켜기 (끄면 운영자가 인사이트 탭에서 켠다)
        </label>
      </Card>

      <Card title="실행자와 데이터 서버">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="실행 사용자 ID (필수)" error={errors.run_as_user_id}>
            <input
              aria-label="실행 사용자 ID"
              value={form.run_as_user_id ?? ''}
              onChange={(e) => set('run_as_user_id', e.target.value || null)}
              className={inputClass}
            />
          </Field>
          {SERVER_FIELDS.map((s) => (
            <Field key={s.key} label={s.label} error={errors[s.key]}>
              {serverItems.length > 0 ? (
                <select
                  aria-label={s.label}
                  value={form[s.key] ?? ''}
                  onChange={(e) => set(s.key, e.target.value || null)}
                  className={inputClass}
                >
                  <option value="">지정 안 함</option>
                  {serverItems.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                      {m.is_active ? '' : ' (비활성)'}
                    </option>
                  ))}
                </select>
              ) : (
                // 서버 목록을 못 읽으면(권한 등) ID 를 직접 넣는다
                <input
                  aria-label={s.label}
                  value={form[s.key] ?? ''}
                  onChange={(e) => set(s.key, e.target.value || null)}
                  className={inputClass}
                  placeholder="MCP 서버 ID"
                />
              )}
            </Field>
          ))}
        </div>
      </Card>

      {canManage && (
        <div className="flex items-center justify-end gap-3">
          {save.isError && (
            <p role="alert" className="text-sm text-danger">
              {marketAnalysisErrorMessage(save.error, '설정을 저장하지 못했습니다.')}
            </p>
          )}
          {save.isSuccess && <p role="status" className="text-sm text-success">저장했습니다.</p>}
          <Button isPending={save.isPending} pendingText="저장 중…" onClick={submit}>
            설정 저장
          </Button>
        </div>
      )}
    </fieldset>
  );
};

const SettingsTab = ({ canManage }: SettingsTabProps) => {
  const query = useMarketSettings();
  const save = useSaveSettings();
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="설정을 불러오지 못했습니다." />;
  const settings = query.data;
  if (!settings) return null;
  return (
    <div className="space-y-5">
      {!canManage && (
        <p className="rounded-xl border border-border bg-surface-muted px-4 py-2 text-sm text-fg-muted">
          보기 권한만 있어 설정을 바꿀 수 없습니다.
        </p>
      )}
      <SwitchRow settings={settings} canManage={canManage} />
      <SettingsForm key={query.dataUpdatedAt} initial={settings} canManage={canManage} save={save} />
      <RoleAgentTable canManage={canManage} />
    </div>
  );
};

export default SettingsTab;
