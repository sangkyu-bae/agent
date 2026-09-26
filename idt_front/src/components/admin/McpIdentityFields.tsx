// mcp-identity-header Design §5.1 — MCP 서버 폼의 "호출자 신원 헤더" 섹션.
// 상태·검증·전송 규칙은 utils/mcpIdentityForm 에 있다. 이 컴포넌트는 입력만 담당한다.
import { useState } from 'react';
import { IDENTITY_CLAIM_SOURCES, IDENTITY_DEFAULTS } from '@/types/mcpServer';
import type { IdentityFormState } from '@/utils/mcpIdentityForm';

interface McpIdentityFieldsProps {
  value: IdentityFormState;
  onChange: (next: IdentityFormState) => void;
  /** 서버에 이미 신원 설정이 있는가 — 비밀을 비워도 기존 값이 유지된다 */
  hasExisting: boolean;
}

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

const McpIdentityFields = ({ value, onChange, hasExisting }: McpIdentityFieldsProps) => {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const set = <K extends keyof IdentityFormState>(key: K, v: IdentityFormState[K]) =>
    onChange({ ...value, [key]: v });

  return (
    <div className="space-y-4 rounded-xl border border-zinc-100 bg-zinc-50/60 p-4">
      <label className="flex items-start gap-2 text-[13px] text-zinc-700">
        <input
          type="checkbox"
          checked={value.enabled}
          aria-label="호출자 신원 헤더 사용"
          onChange={(e) => set('enabled', e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-violet-600"
        />
        <span>
          <span className="font-medium">호출자 신원 헤더 사용</span>
          <span className="mt-1 block text-[12px] text-zinc-500">
            도구를 호출할 때마다 실행 사용자의 서명 토큰을 헤더로 보냅니다.
            사용자별 자원(개인 메일함 등)을 다루는 서버에만 켜세요.
          </span>
        </span>
      </label>

      {value.enabled && (
        <div className="space-y-4">
          <div>
            <label htmlFor="identity-audience" className={labelCls}>
              audience <span className="text-red-400">*</span>
            </label>
            <input
              id="identity-audience"
              type="text"
              value={value.audience}
              onChange={(e) => set('audience', e.target.value)}
              placeholder="예: mcp-outlook-server (서버 MCP_IDENTITY_AUDIENCE 와 동일)"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="identity-secret" className={labelCls}>
              서명 비밀{!hasExisting && <span className="text-red-400"> *</span>}
            </label>
            <input
              id="identity-secret"
              type="password"
              value={value.secret}
              onChange={(e) => set('secret', e.target.value)}
              placeholder={
                hasExisting
                  ? '비우면 기존 유지'
                  : `${IDENTITY_DEFAULTS.min_secret_length}자 이상 — 서버 MCP_IDENTITY_SECRET 과 동일`
              }
              className={inputCls}
              autoComplete="new-password"
            />
          </div>

          <fieldset>
            <legend className={labelCls}>클레임 소스</legend>
            <div className="flex gap-4 text-[13px] text-zinc-700">
              {[
                { v: IDENTITY_CLAIM_SOURCES.MAILBOX_UPN, label: '메일함' },
                { v: IDENTITY_CLAIM_SOURCES.EMAIL, label: '로그인 이메일' },
              ].map((opt) => (
                <label key={opt.v} className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="identity-claim-source"
                    checked={value.claimSource === opt.v}
                    onChange={() => set('claimSource', opt.v)}
                    className="h-4 w-4 border-zinc-300 text-violet-600"
                  />
                  {opt.label}
                </label>
              ))}
            </div>
          </fieldset>

          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            aria-expanded={showAdvanced}
            className="text-[12.5px] font-medium text-zinc-500 hover:text-zinc-700"
          >
            {showAdvanced ? '▾' : '▸'} 고급 설정
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-2 gap-3">
              {(
                [
                  ['headerName', '헤더 이름', 'identity-header-name'],
                  ['claimName', '클레임 이름', 'identity-claim-name'],
                  ['issuer', 'issuer', 'identity-issuer'],
                  ['ttlSeconds', '토큰 수명(초)', 'identity-ttl'],
                ] as const
              ).map(([key, label, id]) => (
                <div key={key}>
                  <label htmlFor={id} className={labelCls}>
                    {label}
                  </label>
                  <input
                    id={id}
                    type="text"
                    value={value[key]}
                    onChange={(e) => set(key, e.target.value)}
                    className={inputCls}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default McpIdentityFields;
