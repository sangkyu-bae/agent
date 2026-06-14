/**
 * Agent 첨부(엑셀 등) 타입 — ws-agent-excel-attachment.
 * 백엔드 계약: idt/src/api/routes/agent_attachment_router.py (AttachmentUploadResponse),
 *             idt/src/api/routes/ws_schemas.py (AttachmentRefPayload)
 */

/** 현재 'excel'만 지원 (확장 가능). */
export type AttachmentType = 'excel';

/** 업로드 응답 — file_id 발급 결과. */
export interface AgentAttachmentUploadResponse {
  file_id: string;
  type: AttachmentType;
  filename: string;
  size: number;
}

/** WS subscribe 메시지에 싣는 첨부 참조. */
export interface AgentAttachmentRef {
  type: AttachmentType;
  file_id: string;
}
