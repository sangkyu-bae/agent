// approval-edit-before-approve Design §5.3 — 수정 후 승인 순수 규칙
// 서버가 키/타입을 다시 검증하므로 여기서는 화면 상태 계산만 한다.

type ArgsRecord = Record<string, unknown>;

/** 편집 폼 초기값 — editable_keys 중 현재 문자열 값만 */
export const buildEditForm = (
  displayArgs: ArgsRecord,
  editableKeys: string[],
): Record<string, string> =>
  Object.fromEntries(
    editableKeys
      .filter((key) => typeof displayArgs[key] === 'string')
      .map((key) => [key, displayArgs[key] as string]),
  );

/** 원본 대비 바뀐 키만 — 요청 바디(edited_args)에 그대로 실린다 */
export const diffEditedArgs = (
  displayArgs: ArgsRecord,
  form: Record<string, string>,
): Record<string, string> =>
  Object.fromEntries(
    Object.entries(form).filter(([key, value]) => displayArgs[key] !== value),
  );

/** 본문 외 필드(수신자 등) 변경 여부 — 확인 다이얼로그 경고 판정 */
export const hasNonBodyChange = (
  changed: Record<string, string>,
  bodyKey: string | null,
): boolean => Object.keys(changed).some((key) => key !== bodyKey);
