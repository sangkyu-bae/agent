export interface Department {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface DepartmentListResponse {
  departments: Department[];
}

export interface CreateDepartmentRequest {
  name: string;
  description?: string;
}

export interface UpdateDepartmentRequest {
  name?: string;
  description?: string;
}

export interface AssignUserDepartmentRequest {
  department_id: string;
  is_primary?: boolean;
}
