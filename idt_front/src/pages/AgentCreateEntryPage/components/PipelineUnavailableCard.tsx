interface PipelineUnavailableCardProps {
  onManualCreate: () => void;
}

/**
 * 파이프라인 킬스위치 off (404) 안내 (Design §5.3 / FR-F15).
 *
 * 서버 `AGENT_PIPELINE_ENABLED` 가 꺼져 있으면 라우터 자체가 등록되지 않아
 * 404 다. 이 경우 위저드를 계속 보여주면 사용자가 눌러도 매번 실패하므로,
 * 화면을 대체하고 유일하게 동작하는 경로(직접 만들기)로 안내한다.
 */
const PipelineUnavailableCard = ({
  onManualCreate,
}: PipelineUnavailableCardProps) => (
  <div
    role="status"
    className="rounded-2xl border border-zinc-200 bg-white p-6 text-center shadow-sm"
  >
    <h3 className="text-[15px] font-semibold text-zinc-900">
      자동 생성이 지금은 사용할 수 없어요
    </h3>
    <p className="mt-1.5 text-[12.5px] leading-relaxed text-zinc-500">
      관리자가 기능을 활성화하면 설명 한 문장으로 에이전트를 만들 수 있습니다.
      <br />
      그때까지는 직접 만들기로 진행해주세요.
    </p>
    <button
      type="button"
      onClick={onManualCreate}
      className="mt-4 rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
    >
      에이전트 직접 만들기
    </button>
  </div>
);

export default PipelineUnavailableCard;
