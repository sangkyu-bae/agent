/**
 * agent-kb-quick-setup — 빌더 원스톱 KB 구성 계약.
 *
 * Design Ref: §3.1 / §4.2 — 백엔드 `knowledge_base_router.py` (/quick),
 * `interfaces/schemas/kb_defaults.py` 와 1:1 대응한다.
 * 런타임 상수는 컴포넌트 파일이 아니라 여기 둔다 (tsx-authoring-pitfalls 위키).
 */
import type { CollectionScope } from '@/types/ragToolConfig';

export const KB_QUICK_DOC_STATUS = {
  UPLOADED: 'uploaded',
  FAILED: 'failed',
} as const;

export type KbQuickDocStatus =
  (typeof KB_QUICK_DOC_STATUS)[keyof typeof KB_QUICK_DOC_STATUS];

export interface QuickKbDocumentResult {
  filename: string;
  status: KbQuickDocStatus;
  document_id: string | null;
  chunk_count: number;
  error: string | null;
}

export interface QuickKbResponse {
  kb_id: string;
  kb_name: string;
  collection_name: string;
  scope: CollectionScope;
  documents: QuickKbDocumentResult[];
  uploaded_count: number;
  failed_count: number;
}

export interface QuickKbRequest {
  name: string;
  scope: CollectionScope;
  departmentId?: string | null;
  files: File[];
}

/** GET /api/v1/kb-defaults — 사용자용 축약 */
export interface KbDefaultsInfo {
  configured: boolean;
  default_embedding_model_id: number | null;
  model_display_name: string | null;
}

export interface KbDefaultsModelSummary {
  id: number;
  provider: string;
  model_name: string;
  display_name: string;
  vector_dimension: number;
  is_active: boolean;
}

/** GET/PUT /api/v1/admin/kb-defaults */
export interface AdminKbDefaultsResponse {
  configured: boolean;
  default_embedding_model_id: number | null;
  model: KbDefaultsModelSummary | null;
  warnings: string[];
  updated_at: string | null;
}

export interface AdminKbDefaultsUpdateRequest {
  default_embedding_model_id: number;
}

export const KB_QUICK_MAX_FILES = 10;
/** KbUploadDocumentModal 과 동일 — 새 포맷은 백엔드 파서 라우팅 + 양쪽 accept */
export const KB_QUICK_ACCEPT = '.pdf,.xlsx,.xls,.hwp,.hwpx';

export const KB_DEFAULTS_NOT_CONFIGURED_CODE = 'KB_DEFAULTS_NOT_CONFIGURED';
export const KB_DEFAULTS_NOT_CONFIGURED_MESSAGE =
  '관리자가 기본 임베딩 모델을 설정해야 합니다';

/** 블록 진행 카드 3단계 라벨 (Design §5.4) */
export const KB_QUICK_STEP_LABELS = {
  create: '지식베이스 만들기',
  upload: '문서 올리기',
  attach: '도구 연결',
} as const;

/** 자동 생성 KB 이름 규칙 (Design §3.1) */
export const KB_QUICK_NAME_SUFFIX = ' 지식';
export const KB_QUICK_FALLBACK_NAME = '새 에이전트 지식';
export const KB_NAME_MAX_LENGTH = 100;
