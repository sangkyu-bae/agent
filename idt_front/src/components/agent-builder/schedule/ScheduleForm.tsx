import { useState } from 'react';
import type {
  ScheduleCreateRequest,
  ScheduleResponse,
} from '@/types/agentSchedule';
import {
  DEFAULT_SCHEDULE_TIMEZONE,
  MAX_INSTRUCTION_LENGTH,
  SCHEDULE_TYPE,
} from '@/types/agentSchedule';
import {
  buildCronExpr,
  parseCronExpr,
  validateCronExpr,
  generateScheduleName,
  DEFAULT_CRON_FORM,
  CRON_DOW_LABELS,
  type CronFormValue,
} from '@/utils/scheduleCron';

interface ScheduleFormProps {
  /** null/undefined = 신규 작성, 값 = 해당 스케줄 수정 */
  initial?: ScheduleResponse | null;
  isSubmitting: boolean;
  /** 서버 400 검증 메시지 표출 */
  submitError: string | null;
  onSubmit: (payload: ScheduleCreateRequest) => void;
  onCancel: () => void;
}

type ScheduleKind = 'recurring' | 'once';
type InputMode = 'form' | 'expr';

const range = (from: number, to: number) =>
  Array.from({ length: to - from + 1 }, (_, i) => from + i);

const selectClass =
  'w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-[13.5px] text-zinc-900 outline-none transition-colors focus:border-violet-400';

/** 로컬 기준 YYYY-MM-DD — once 과거 날짜 차단용 */
const toDateString = (date: Date) => {
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${m}-${d}`;
};

const todayString = () => toDateString(new Date());

/** date input min 속성용 — API 제약(미래 날짜)에 맞춰 내일부터 선택 가능 */
const tomorrowString = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return toDateString(d);
};

/**
 * 스케줄 입력 폼 — docs/img/schedule.png 사양.
 * 반복(cron_expr)/1회(once) 유형, 폼/표현식 입력, 미리보기, 실행 메시지.
 * agent-schedule Design §4.1.
 */
const ScheduleForm = ({
  initial,
  isSubmitting,
  submitError,
  onSubmit,
  onCancel,
}: ScheduleFormProps) => {
  const initialCronForm = initial?.spec.cron_expr
    ? parseCronExpr(initial.spec.cron_expr)
    : null;

  const [kind, setKind] = useState<ScheduleKind>(
    initial?.spec.schedule_type === SCHEDULE_TYPE.ONCE ? 'once' : 'recurring',
  );
  const [inputMode, setInputMode] = useState<InputMode>(
    initial?.spec.cron_expr && !initialCronForm ? 'expr' : 'form',
  );
  const [cronForm, setCronForm] = useState<CronFormValue>(
    initialCronForm ?? DEFAULT_CRON_FORM,
  );
  const [cronExprInput, setCronExprInput] = useState(
    initial?.spec.cron_expr ?? buildCronExpr(DEFAULT_CRON_FORM),
  );
  const [runDate, setRunDate] = useState(initial?.spec.run_date ?? '');
  const [timeOfDay, setTimeOfDay] = useState(initial?.spec.time_of_day ?? '09:00');
  const [instruction, setInstruction] = useState(initial?.instruction ?? '');
  const [clientError, setClientError] = useState<string | null>(null);

  const preview = inputMode === 'form' ? buildCronExpr(cronForm) : cronExprInput;
  const isEdit = !!initial;

  const setCronField = (key: keyof CronFormValue) => (value: string) =>
    setCronForm((prev) => ({ ...prev, [key]: value }));

  const handleSubmit = () => {
    const trimmed = instruction.trim();
    if (!trimmed) {
      setClientError('실행 메시지를 입력해주세요.');
      return;
    }
    if (trimmed.length > MAX_INSTRUCTION_LENGTH) {
      setClientError(`실행 메시지는 최대 ${MAX_INSTRUCTION_LENGTH}자입니다.`);
      return;
    }

    let spec: ScheduleCreateRequest['spec'];
    if (kind === 'recurring') {
      const result = validateCronExpr(preview);
      if (!result.valid) {
        setClientError(result.error ?? '스케줄 표현식이 올바르지 않습니다.');
        return;
      }
      spec = { schedule_type: SCHEDULE_TYPE.CRON, cron_expr: preview };
    } else {
      if (!runDate) {
        setClientError('실행 날짜를 선택해주세요.');
        return;
      }
      if (runDate <= todayString()) {
        setClientError('실행 날짜는 미래 날짜여야 합니다.');
        return;
      }
      if (!timeOfDay) {
        setClientError('실행 시각을 선택해주세요.');
        return;
      }
      spec = {
        schedule_type: SCHEDULE_TYPE.ONCE,
        run_date: runDate,
        time_of_day: timeOfDay,
      };
    }

    setClientError(null);
    onSubmit({
      name: generateScheduleName(spec),
      spec,
      instruction: trimmed,
      timezone: DEFAULT_SCHEDULE_TIMEZONE,
      enabled: initial?.enabled ?? true,
    });
  };

  const error = clientError ?? submitError;

  return (
    <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-5">
      {/* 스케줄 유형 */}
      <p className="text-[13px] font-semibold text-zinc-900">스케줄 유형</p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          onClick={() => setKind('recurring')}
          className={`flex items-center gap-1.5 rounded-xl border px-4 py-2 text-[13px] font-medium transition-all ${
            kind === 'recurring'
              ? 'border-zinc-900 bg-zinc-900 text-white'
              : 'border-zinc-300 bg-white text-zinc-600 hover:border-zinc-400'
          }`}
        >
          반복
        </button>
        <button
          type="button"
          onClick={() => setKind('once')}
          className={`flex items-center gap-1.5 rounded-xl border px-4 py-2 text-[13px] font-medium transition-all ${
            kind === 'once'
              ? 'border-zinc-900 bg-zinc-900 text-white'
              : 'border-zinc-300 bg-white text-zinc-600 hover:border-zinc-400'
          }`}
        >
          1회
        </button>
      </div>

      {kind === 'recurring' ? (
        <>
          {/* 입력 방식 세그먼트 */}
          <p className="mt-5 text-[13px] font-semibold text-zinc-900">스케줄 표현식</p>
          <div className="mt-2 grid grid-cols-2 overflow-hidden rounded-xl border border-zinc-300">
            <button
              type="button"
              onClick={() => setInputMode('form')}
              className={`py-2 text-[13px] font-medium transition-colors ${
                inputMode === 'form' ? 'bg-zinc-900 text-white' : 'bg-white text-zinc-500'
              }`}
            >
              폼
            </button>
            <button
              type="button"
              onClick={() => {
                setCronExprInput(buildCronExpr(cronForm));
                setInputMode('expr');
              }}
              className={`py-2 text-[13px] font-medium transition-colors ${
                inputMode === 'expr' ? 'bg-zinc-900 text-white' : 'bg-white text-zinc-500'
              }`}
            >
              스케줄 표현식
            </button>
          </div>

          {inputMode === 'form' ? (
            <div className="mt-4 flex flex-col gap-3">
              {/* 분 */}
              <div className="flex items-center gap-4">
                <span className="w-10 shrink-0 text-[13px] text-zinc-600">분</span>
                <select
                  aria-label="분"
                  value={cronForm.minute}
                  onChange={(e) => setCronField('minute')(e.target.value)}
                  className={selectClass}
                >
                  {range(0, 59).map((m) => (
                    <option key={m} value={String(m)}>{m}</option>
                  ))}
                </select>
              </div>
              {/* 시 */}
              <div className="flex items-center gap-4">
                <span className="w-10 shrink-0 text-[13px] text-zinc-600">시</span>
                <select
                  aria-label="시"
                  value={cronForm.hour}
                  onChange={(e) => setCronField('hour')(e.target.value)}
                  className={selectClass}
                >
                  <option value="*">매시</option>
                  {range(0, 23).map((h) => (
                    <option key={h} value={String(h)}>{h}</option>
                  ))}
                </select>
              </div>
              {/* 일 */}
              <div className="flex items-center gap-4">
                <span className="w-10 shrink-0 text-[13px] text-zinc-600">일</span>
                <select
                  aria-label="일"
                  value={cronForm.dayOfMonth}
                  onChange={(e) => setCronField('dayOfMonth')(e.target.value)}
                  className={selectClass}
                >
                  <option value="*">매일</option>
                  {range(1, 31).map((d) => (
                    <option key={d} value={String(d)}>{d}일</option>
                  ))}
                </select>
              </div>
              {/* 월 */}
              <div className="flex items-center gap-4">
                <span className="w-10 shrink-0 text-[13px] text-zinc-600">월</span>
                <select
                  aria-label="월"
                  value={cronForm.month}
                  onChange={(e) => setCronField('month')(e.target.value)}
                  className={selectClass}
                >
                  <option value="*">매월</option>
                  {range(1, 12).map((m) => (
                    <option key={m} value={String(m)}>{m}월</option>
                  ))}
                </select>
              </div>
              {/* 요일 */}
              <div className="flex items-center gap-4">
                <span className="w-10 shrink-0 text-[13px] text-zinc-600">요일</span>
                <select
                  aria-label="요일"
                  value={cronForm.dayOfWeek}
                  onChange={(e) => setCronField('dayOfWeek')(e.target.value)}
                  className={selectClass}
                >
                  <option value="*">매일</option>
                  {CRON_DOW_LABELS.map((label, i) => (
                    <option key={label} value={String(i)}>{label}요일</option>
                  ))}
                </select>
              </div>
            </div>
          ) : (
            <input
              type="text"
              aria-label="cron 표현식"
              value={cronExprInput}
              onChange={(e) => setCronExprInput(e.target.value)}
              placeholder="분 시 일 월 요일 (예: 0 9 * * *)"
              className="mt-4 w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 font-mono text-[13.5px] text-zinc-900 outline-none transition-colors focus:border-violet-400"
            />
          )}

          {/* 미리보기 */}
          <div className="mt-3 rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-[13px] text-zinc-500">
            미리보기: <span className="font-mono tracking-widest text-zinc-800">{preview}</span>
          </div>
        </>
      ) : (
        <div className="mt-5 flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <span className="w-16 shrink-0 text-[13px] text-zinc-600">실행 날짜</span>
            <input
              type="date"
              aria-label="실행 날짜"
              value={runDate}
              min={tomorrowString()}
              onChange={(e) => setRunDate(e.target.value)}
              className={selectClass}
            />
          </div>
          <div className="flex items-center gap-4">
            <span className="w-16 shrink-0 text-[13px] text-zinc-600">실행 시각</span>
            <input
              type="time"
              aria-label="실행 시각"
              value={timeOfDay}
              onChange={(e) => setTimeOfDay(e.target.value)}
              className={selectClass}
            />
          </div>
        </div>
      )}

      {/* 타임존 (고정) */}
      <p className="mt-5 text-[13px] font-semibold text-zinc-900">타임존</p>
      <div className="mt-2 rounded-xl border border-zinc-200 bg-zinc-100 px-4 py-2.5 text-[13.5px] text-zinc-500">
        {DEFAULT_SCHEDULE_TIMEZONE}
      </div>

      {/* 실행 메시지 */}
      <p className="mt-5 text-[13px] font-semibold text-zinc-900">실행 메시지</p>
      <textarea
        aria-label="실행 메시지"
        value={instruction}
        onChange={(e) => setInstruction(e.target.value)}
        rows={3}
        placeholder="에이전트에게 보낼 메시지를 입력하세요"
        className="mt-2 block w-full resize-none rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-[13.5px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none transition-colors focus:border-violet-400"
      />
      <div className="mt-1.5 flex items-center justify-between text-[12px] text-zinc-400">
        <span>{'{today} {now} {weekday}'} 변수를 사용할 수 있어요</span>
        <span>
          {instruction.trim().length}/{MAX_INSTRUCTION_LENGTH}
        </span>
      </div>

      {error && (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
      )}

      {/* 액션 */}
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
        >
          취소
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={isSubmitting}
          className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
        >
          {isEdit ? '저장' : '생성'}
        </button>
      </div>
    </div>
  );
};

export default ScheduleForm;
