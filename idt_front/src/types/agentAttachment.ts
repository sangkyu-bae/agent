/**
 * Agent 첨부(엑셀·이미지) 타입 — ws-agent-excel-attachment / chat-image-attachment.
 * 백엔드 계약: idt/src/api/routes/agent_attachment_router.py (AttachmentUploadResponse),
 *             idt/src/api/routes/ws_schemas.py (AttachmentRefPayload)
 * Design Ref: chat-image-attachment §4.2 / §5.3
 */

/** 'excel' | 'image' — 권위 있는 타입은 서버가 판별해 응답한다. */
export type AttachmentType = 'excel' | 'image';

/** 업로드 응답 — file_id 발급 결과. width/height 는 이미지일 때만 채워진다. */
export interface AgentAttachmentUploadResponse {
  file_id: string;
  type: AttachmentType;
  filename: string;
  size: number;
  width?: number | null;
  height?: number | null;
}

/** WS subscribe 메시지에 싣는 첨부 참조. */
export interface AgentAttachmentRef {
  type: AttachmentType;
  file_id: string;
}

/** 전송 대기 중인 첨부 1건 (칩 표시용). previewUrl 은 이미지의 object URL. */
export interface PendingAttachment {
  id: string;
  ref: AgentAttachmentRef;
  name: string;
  previewUrl?: string;
}

/** 이미지 첨부 제한 — 서버 설정(agent_attachment_image_*)과 같은 기본값. */
export const IMAGE_ATTACHMENT_LIMITS = {
  maxCount: 5,
  maxBytes: 10 * 1024 * 1024,
  mimeTypes: ['image/png', 'image/jpeg', 'image/webp'],
  extensions: ['.png', '.jpg', '.jpeg', '.webp'],
  accept: 'image/png,image/jpeg,image/webp',
} as const;

/** 프론트 사전 검증 거절 사유. */
export const IMAGE_REJECT_REASON = {
  UNSUPPORTED_TYPE: 'unsupported_type',
  TOO_LARGE: 'too_large',
  TOO_MANY: 'too_many',
} as const;
export type ImageRejectReason = (typeof IMAGE_REJECT_REASON)[keyof typeof IMAGE_REJECT_REASON];

/** 서버 subscribe 거절 코드 → 사용자 안내. 미지 코드는 기존 `[code] message` 표시를 따른다. */
export const ATTACHMENT_ERROR_MESSAGES = {
  VISION_NOT_SUPPORTED:
    '이 에이전트의 모델은 이미지 입력을 지원하지 않습니다. 관리자 > LLM 모델에서 비전 지원을 켜거나 다른 에이전트를 사용하세요.',
  ATTACHMENT_LIMIT_EXCEEDED: `이미지는 최대 ${IMAGE_ATTACHMENT_LIMITS.maxCount}장까지 첨부할 수 있습니다.`,
  ATTACHMENT_NOT_FOUND: '첨부 파일이 만료되었거나 찾을 수 없습니다. 다시 첨부해 주세요.',
  ATTACHMENT_ACCESS_DENIED: '첨부 파일에 접근할 수 없습니다. 다시 첨부해 주세요.',
} as const;
export type AttachmentErrorCode = keyof typeof ATTACHMENT_ERROR_MESSAGES;

export const VISION_DISABLED_REASON =
  '이 에이전트의 모델은 이미지 입력을 지원하지 않습니다 (관리자 > LLM 모델에서 비전 지원을 켜세요)';
