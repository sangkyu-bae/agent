export const TOOL_PARAM_TYPE = {
  string: 'string',
  number: 'number',
  boolean: 'boolean',
  array: 'array',
  object: 'object',
} as const;

export type ToolParamType = (typeof TOOL_PARAM_TYPE)[keyof typeof TOOL_PARAM_TYPE];

export const TOOL_PARAM_TYPE_LABEL: Record<ToolParamType, string> = {
  string: '문자열',
  number: '숫자',
  boolean: '불리언',
  array: '배열',
  object: '객체',
};

export const HTTP_METHOD = {
  GET: 'GET',
  POST: 'POST',
  PUT: 'PUT',
  PATCH: 'PATCH',
  DELETE: 'DELETE',
} as const;

export type HttpMethod = (typeof HTTP_METHOD)[keyof typeof HTTP_METHOD];

export interface ToolSchemaParam {
  id: string;
  name: string;
  type: ToolParamType;
  description: string;
  required: boolean;
}

export interface ToolEndpoint {
  id: string;
  method: HttpMethod;
  path: string;
  description: string;
}

export interface AdminTool {
  id: string;
  name: string;
  description: string;
  category: string;
  schemaParams: ToolSchemaParam[];
  endpoints: ToolEndpoint[];
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AdminToolFormData {
  name: string;
  description: string;
  category: string;
  schemaParams: Omit<ToolSchemaParam, 'id'>[];
  endpoints: Omit<ToolEndpoint, 'id'>[];
}

// API Request/Response types (서버 연동 준비)
export interface AdminToolCreateRequest {
  name: string;
  description: string;
  category: string;
  schemaParams: Omit<ToolSchemaParam, 'id'>[];
  endpoints: Omit<ToolEndpoint, 'id'>[];
}

export interface AdminToolUpdateRequest extends Partial<AdminToolCreateRequest> {}

export interface AdminToolCreateResponse extends AdminTool {}
export interface AdminToolUpdateResponse extends AdminTool {}
export interface AdminToolDeleteResponse {
  id: string;
  deleted: boolean;
}
