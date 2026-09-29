export class ApiError extends Error {
  status: number;
  /** 백엔드 detail 이 {code, message} 객체일 때의 오류 코드 (없으면 undefined) */
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}
