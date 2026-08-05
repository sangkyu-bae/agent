import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  MiddlewareCatalogItem,
  MiddlewareCatalogResponse,
  SetMiddlewareFlagsRequest,
} from '@/types/middleware';

export const middlewareService = {
  getMiddlewareCatalog: () =>
    authApiClient.get<MiddlewareCatalogResponse>(API_ENDPOINTS.MIDDLEWARE_CATALOG),
  // builtin-middleware D4: 관리자 전용 빌트인/강제/기본 설정 부분 갱신
  setMiddlewareFlags: (middlewareType: string, body: SetMiddlewareFlagsRequest) =>
    authApiClient.patch<MiddlewareCatalogItem>(
      API_ENDPOINTS.MIDDLEWARE_CATALOG_DETAIL(middlewareType),
      body,
    ),
};
