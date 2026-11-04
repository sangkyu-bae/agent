export class ApiError extends Error {
  status: number;
  /** 백엔드 detail 이 {code, message} 객체일 때의 오류 코드 (없으면 undefined) */
  code?: string;
  /**
   * tool-access-control §4.2 (additive): detail 이 객체일 때 원본 그대로.
   * TOOL_ACCESS_DENIED 의 tool_ids 처럼 code·message 외 필드를 쓰는 화면용.
   */
  detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}
