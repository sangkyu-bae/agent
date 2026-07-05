import { useState } from 'react';
import Dropdown from '@/components/common/Dropdown';
import {
  useMcpServers,
  useCreateMcpServer,
  useUpdateMcpServer,
  useDeleteMcpServer,
  useTestMcpConnection,
} from '@/hooks/useMcpServers';
import { useAuthStore } from '@/store/authStore';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import Modal from '@/components/common/Modal';
import type {
  McpServer,
  McpTransport,
  RegisterMcpServerRequest,
  UpdateMcpServerRequest,
  McpConnectionTestResponse,
} from '@/types/mcpServer';

const inputCls =
  'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

interface FormState {
  name: string;
  description: string;
  endpoint: string;
  transport: McpTransport;
  is_active: boolean;
  apiKey: string;
  profile: string;
  headersText: string;
  serverConfigText: string;
}

const emptyForm: FormState = {
  name: '',
  description: '',
  endpoint: '',
  transport: 'sse',
  is_active: true,
  apiKey: '',
  profile: '',
  headersText: '',
  serverConfigText: '',
};

const fromServer = (s: McpServer): FormState => ({
  name: s.name,
  description: s.description,
  endpoint: s.endpoint,
  transport: s.transport,
  is_active: s.is_active,
  // 시크릿은 마스킹되어 오므로 빈 값으로 시작 (변경 시에만 입력)
  apiKey: '',
  profile: '',
  headersText: '',
  serverConfigText: '',
});

/** 비어있지 않은 JSON 텍스트를 객체로 파싱. 실패 시 throw. */
const parseJsonObject = (text: string, label: string): Record<string, unknown> => {
  const parsed = JSON.parse(text);
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error(`${label}은(는) JSON 객체여야 합니다.`);
  }
  return parsed as Record<string, unknown>;
};

/** 폼 상태 → auth_config 객체 (입력된 항목만). 비면 undefined. */
const buildAuthConfig = (f: FormState): Record<string, unknown> | undefined => {
  const auth: Record<string, unknown> = {};
  if (f.apiKey.trim()) auth.api_key = f.apiKey.trim();
  if (f.profile.trim()) auth.profile = f.profile.trim();
  if (f.headersText.trim()) auth.headers = parseJsonObject(f.headersText, 'Headers');
  return Object.keys(auth).length > 0 ? auth : undefined;
};

interface FormModalProps {
  isOpen: boolean;
  server: McpServer | null; // null = 생성
  onClose: () => void;
  onSubmitCreate: (req: Omit<RegisterMcpServerRequest, 'user_id'>) => void;
  onSubmitUpdate: (data: UpdateMcpServerRequest) => void;
  isPending: boolean;
  error: string | null;
  setError: (msg: string | null) => void;
}

const McpServerFormModal = ({
  isOpen,
  server,
  onClose,
  onSubmitCreate,
  onSubmitUpdate,
  isPending,
  error,
  setError,
}: FormModalProps) => {
  const isEdit = !!server;
  const [form, setForm] = useState<FormState>(emptyForm);
  const [initialized, setInitialized] = useState(false);
  const testMutation = useTestMcpConnection();
  const [testResult, setTestResult] = useState<McpConnectionTestResponse | null>(null);

  // 모달이 열릴 때 1회 초기화
  if (isOpen && !initialized) {
    setForm(server ? fromServer(server) : emptyForm);
    setTestResult(null);
    setInitialized(true);
  }
  if (!isOpen && initialized) setInitialized(false);
  if (!isOpen) return null;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!form.name.trim() || !form.description.trim() || !form.endpoint.trim()) {
      setError('이름·설명·엔드포인트는 필수입니다.');
      return;
    }
    if (form.transport === 'streamable_http' && !isEdit && !form.apiKey.trim()) {
      setError('Streamable HTTP는 API Key가 필요합니다.');
      return;
    }

    let authConfig: Record<string, unknown> | undefined;
    let serverConfig: Record<string, unknown> | undefined;
    try {
      authConfig = buildAuthConfig(form);
      serverConfig = form.serverConfigText.trim()
        ? parseJsonObject(form.serverConfigText, 'Server Config')
        : undefined;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'JSON 형식 오류');
      return;
    }

    if (isEdit) {
      const data: UpdateMcpServerRequest = {
        name: form.name.trim(),
        description: form.description.trim(),
        endpoint: form.endpoint.trim(),
        transport: form.transport,
        is_active: form.is_active,
      };
      // 시크릿: 입력된 경우에만 전송 (빈 값 = 기존 유지)
      if (authConfig) data.auth_config = authConfig;
      if (serverConfig) data.server_config = serverConfig;
      onSubmitUpdate(data);
    } else {
      onSubmitCreate({
        name: form.name.trim(),
        description: form.description.trim(),
        endpoint: form.endpoint.trim(),
        transport: form.transport,
        auth_config: authConfig ?? null,
        server_config: serverConfig ?? null,
      });
    }
  };

  const handleTest = () => {
    if (!server) return;
    setTestResult(null);
    testMutation.mutate(server.id, { onSuccess: (res) => setTestResult(res) });
  };

  const isStreamable = form.transport === 'streamable_http';

  return (
    <Modal
      onClose={onClose}
      title={isEdit ? 'MCP 서버 수정' : 'MCP 서버 등록'}
      size="lg"
      scroll="content"
      showCloseButton={false}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className={labelCls}>
              이름 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="예: Naver Search"
              maxLength={255}
              className={inputCls}
              autoFocus
            />
          </div>

          <div>
            <label className={labelCls}>
              설명 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => set('description', e.target.value)}
              placeholder="서버에 대한 설명"
              className={inputCls}
            />
          </div>

          <div>
            <label className={labelCls}>
              엔드포인트 (http/https) <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={form.endpoint}
              onChange={(e) => set('endpoint', e.target.value)}
              placeholder="https://server.example.com/mcp"
              maxLength={512}
              className={inputCls}
            />
          </div>

          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className={labelCls}>Transport</label>
              <Dropdown
                value={form.transport}
                onChange={(v) => set('transport', v as McpTransport)}
                options={[
                  { value: 'sse', label: 'SSE' },
                  { value: 'streamable_http', label: 'Streamable HTTP' },
                ]}
                className="w-full"
              />
            </div>
            {isEdit && (
              <label className="mt-6 flex items-center gap-2 text-[13px] text-zinc-700">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => set('is_active', e.target.checked)}
                  className="h-4 w-4 rounded border-zinc-300 text-violet-600"
                />
                활성
              </label>
            )}
          </div>

          {/* 시크릿 영역 */}
          <div className="space-y-4 rounded-xl border border-zinc-100 bg-zinc-50/60 p-4">
            <p className="text-[12px] font-medium text-zinc-500">
              인증 / 서버 설정
              {isEdit && (
                <span className="ml-1 text-zinc-400">
                  — 기존 값은 마스킹(****)되며, 변경 시에만 입력하세요.
                </span>
              )}
            </p>

            <div>
              <label className={labelCls}>
                API Key{isStreamable && !isEdit && <span className="text-red-400"> *</span>}
              </label>
              <input
                type="password"
                value={form.apiKey}
                onChange={(e) => set('apiKey', e.target.value)}
                placeholder={isEdit ? '변경 시에만 입력' : 'Smithery 등 플랫폼 API Key'}
                className={inputCls}
                autoComplete="new-password"
              />
            </div>

            {isStreamable && (
              <div>
                <label className={labelCls}>Profile (선택)</label>
                <input
                  type="text"
                  value={form.profile}
                  onChange={(e) => set('profile', e.target.value)}
                  placeholder="Smithery profile"
                  className={inputCls}
                />
              </div>
            )}

            <div>
              <label className={labelCls}>Headers (선택, JSON)</label>
              <textarea
                value={form.headersText}
                onChange={(e) => set('headersText', e.target.value)}
                placeholder='{"X-Custom": "value"}'
                rows={2}
                className={`${inputCls} font-mono text-[12.5px]`}
              />
            </div>

            {isStreamable && (
              <div>
                <label className={labelCls}>Server Config (선택, JSON)</label>
                <textarea
                  value={form.serverConfigText}
                  onChange={(e) => set('serverConfigText', e.target.value)}
                  placeholder='{"NAVER_CLIENT_ID": "...", "NAVER_CLIENT_SECRET": "..."}'
                  rows={2}
                  className={`${inputCls} font-mono text-[12.5px]`}
                />
              </div>
            )}
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
          )}

          {/* 연결 테스트 (저장된 서버만) */}
          {isEdit && (
            <div className="rounded-xl border border-zinc-100 p-3">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-zinc-600">연결 테스트</span>
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testMutation.isPending}
                  className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-300 hover:text-violet-600 active:scale-95 disabled:opacity-50"
                >
                  {testMutation.isPending ? '테스트 중...' : '연결 테스트'}
                </button>
              </div>
              {testResult && <TestResultView result={testResult} />}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              {isPending ? '저장 중...' : isEdit ? '저장' : '등록'}
            </button>
          </div>
      </form>
    </Modal>
  );
};

const TestResultView = ({ result }: { result: McpConnectionTestResponse }) => {
  if (result.ok) {
    return (
      <div className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-700">
        <p className="font-medium">
          연결 성공 — 도구 {result.tools?.length ?? 0}개
          {typeof result.elapsed_ms === 'number' && ` (${result.elapsed_ms}ms)`}
        </p>
        {result.tools && result.tools.length > 0 && (
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {result.tools.map((t) => (
              <li key={t.name}>
                <span className="font-mono">{t.name}</span>
                {t.description && <span className="text-emerald-600"> — {t.description}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-600">
      연결 실패: {result.error ?? '알 수 없는 오류'}
    </div>
  );
};

const TRANSPORT_LABEL: Record<McpTransport, string> = {
  sse: 'SSE',
  streamable_http: 'Streamable HTTP',
};

const AdminMcpServersPage = () => {
  const { data, isLoading, isError, refetch } = useMcpServers();
  const servers = data?.items ?? [];
  const userId = useAuthStore((s) => s.user?.id);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editing, setEditing] = useState<McpServer | null>(null);
  const [deleting, setDeleting] = useState<McpServer | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [rowTest, setRowTest] = useState<{ server: McpServer; result: McpConnectionTestResponse | null } | null>(null);

  const createMutation = useCreateMcpServer();
  const updateMutation = useUpdateMcpServer();
  const deleteMutation = useDeleteMcpServer();
  const rowTestMutation = useTestMcpConnection();

  const apiError = (err: unknown, fallback: string) =>
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback;

  const handleCreate = (req: Omit<RegisterMcpServerRequest, 'user_id'>) => {
    if (userId == null) {
      setFormError('로그인 정보를 확인할 수 없습니다.');
      return;
    }
    createMutation.mutate(
      { ...req, user_id: String(userId) },
      {
        onSuccess: () => setIsCreateOpen(false),
        onError: (err) => setFormError(apiError(err, 'MCP 서버 등록에 실패했습니다.')),
      },
    );
  };

  const handleUpdate = (dataReq: UpdateMcpServerRequest) => {
    if (!editing) return;
    updateMutation.mutate(
      { id: editing.id, data: dataReq },
      {
        onSuccess: () => setEditing(null),
        onError: (err) => setFormError(apiError(err, 'MCP 서버 수정에 실패했습니다.')),
      },
    );
  };

  const handleDelete = () => {
    if (!deleting) return;
    deleteMutation.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
  };

  const handleRowTest = (server: McpServer) => {
    setRowTest({ server, result: null });
    rowTestMutation.mutate(server.id, {
      onSuccess: (res) => setRowTest({ server, result: res }),
      onError: () =>
        setRowTest({ server, result: { ok: false, error: '요청 실패' } }),
    });
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">Admin</p>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900">MCP 서버 관리</h1>
          <p className="mt-1 text-[13px] text-zinc-400">
            MCP 서버를 등록·수정·삭제하고 연결을 테스트합니다.
          </p>
        </div>
        <button
          onClick={() => { setFormError(null); setIsCreateOpen(true); }}
          className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          서버 등록
        </button>
      </div>

      {isLoading ? (
        <div className="flex h-48 items-center justify-center text-zinc-400">로딩 중...</div>
      ) : isError ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">MCP 서버 목록을 불러오지 못했습니다.</p>
          <button
            onClick={() => refetch()}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
          >
            다시 시도
          </button>
        </div>
      ) : servers.length === 0 ? (
        <div className="flex h-48 flex-col items-center justify-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50">
          <p className="text-[14px] text-zinc-400">등록된 MCP 서버가 없습니다.</p>
          <button
            onClick={() => { setFormError(null); setIsCreateOpen(true); }}
            className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            + 첫 번째 서버 등록하기
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-100 bg-zinc-50">
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">이름</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">엔드포인트</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">Transport</th>
                <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">상태</th>
                <th className="w-[180px] px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">액션</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {servers.map((srv) => (
                <tr key={srv.id} className="transition-colors hover:bg-zinc-50/50">
                  <td className="px-5 py-4">
                    <div className="text-[14px] font-medium text-zinc-900">{srv.name}</div>
                    <div className="text-[12px] text-zinc-400">{srv.description}</div>
                  </td>
                  <td className="max-w-[220px] truncate px-5 py-4 text-[12.5px] text-zinc-500" title={srv.endpoint}>
                    {srv.endpoint}
                  </td>
                  <td className="px-5 py-4">
                    <span className="rounded-md bg-violet-50 px-2 py-1 text-[11.5px] font-medium text-violet-600">
                      {TRANSPORT_LABEL[srv.transport]}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className={`rounded-md px-2 py-1 text-[11.5px] font-medium ${
                        srv.is_active ? 'bg-emerald-50 text-emerald-600' : 'bg-zinc-100 text-zinc-400'
                      }`}
                    >
                      {srv.is_active ? '활성' : '비활성'}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => handleRowTest(srv)}
                        disabled={rowTestMutation.isPending}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-violet-200 hover:text-violet-600 active:scale-95 disabled:opacity-50"
                      >
                        테스트
                      </button>
                      <button
                        onClick={() => { setFormError(null); setEditing(srv); }}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 active:scale-95"
                      >
                        수정
                      </button>
                      <button
                        onClick={() => setDeleting(srv)}
                        aria-label={`${srv.name} 삭제`}
                        className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-red-200 hover:bg-red-50 hover:text-red-500 active:scale-95"
                      >
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 생성 모달 */}
      <McpServerFormModal
        isOpen={isCreateOpen}
        server={null}
        onClose={() => setIsCreateOpen(false)}
        onSubmitCreate={handleCreate}
        onSubmitUpdate={() => {}}
        isPending={createMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 수정 모달 */}
      <McpServerFormModal
        isOpen={!!editing}
        server={editing}
        onClose={() => setEditing(null)}
        onSubmitCreate={() => {}}
        onSubmitUpdate={handleUpdate}
        isPending={updateMutation.isPending}
        error={formError}
        setError={setFormError}
      />

      {/* 행 단위 테스트 결과 모달 */}
      {rowTest && (
        <Modal
          onClose={() => setRowTest(null)}
          title={`연결 테스트 — ${rowTest.server.name}`}
          size="md"
          showCloseButton={false}
          footer={
            <button
              onClick={() => setRowTest(null)}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:bg-zinc-100"
            >
              닫기
            </button>
          }
        >
          {rowTest.result ? (
            <TestResultView result={rowTest.result} />
          ) : (
            <p className="text-[13px] text-zinc-400">테스트 중...</p>
          )}
        </Modal>
      )}

      {/* 삭제 확인 */}
      <ConfirmDialog
        isOpen={!!deleting}
        title="MCP 서버 삭제"
        description={`"${deleting?.name}" 서버를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`}
        confirmLabel="삭제"
        variant="danger"
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
};

export default AdminMcpServersPage;
