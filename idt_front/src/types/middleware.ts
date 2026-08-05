// builtin-middleware D10: 미들웨어 카탈로그 타입 (GET /api/v1/middleware-catalog)
export interface MiddlewareCatalogItem {
  middleware_type: string;
  name: string;
  description: string;
  /** 빌트인 — 에이전트 생성 시 기본 적용 (사용자 해제 가능, 관리자 토글) */
  is_builtin: boolean;
  /** 강제 — 실행 시 스냅샷과 무관하게 항상 적용 (사용자 해제 불가, 관리자 토글) */
  is_enforced: boolean;
  /** 기본 설정값 — 런타임 단일 소스 (관리자 편집, 사용자는 열람만) */
  default_config: Record<string, unknown>;
  is_active: boolean;
  sort_order: number;
}

export interface MiddlewareCatalogResponse {
  middlewares: MiddlewareCatalogItem[];
}

// PATCH /api/v1/middleware-catalog/{middleware_type} — 부분 갱신 (관리자 전용)
export interface SetMiddlewareFlagsRequest {
  is_builtin?: boolean;
  is_enforced?: boolean;
  default_config?: Record<string, unknown>;
}
