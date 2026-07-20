export type UserStatus = 'pending' | 'approved' | 'rejected';
export type UserRole = 'user' | 'admin';

// expose-user-department: /me 응답에 소속 부서 노출
export interface DepartmentBrief {
  id: string;
  name: string;
  is_primary: boolean;
}

export interface User {
  id: number;
  // expose-user-department: /me가 소속 부서를 함께 반환 (다른 응답에는 없어 optional)
  departments?: DepartmentBrief[];
  email: string;
  role: UserRole;
  status: UserStatus;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: 'bearer';
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface RegisterResponse {
  id: number;
  email: string;
  role: UserRole;
  status: UserStatus;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface PendingUser {
  id: number;
  email: string;
  role: UserRole;
  created_at: string;
}

// ── admin-user-registration ──────────────────────────────
export interface AdminCreateUserRequest {
  email: string;
  password: string;
  display_name: string;
  position?: string;
  employee_no?: string;
  joined_at?: string; // YYYY-MM-DD
  role: UserRole;
  department_id?: string;
}

export interface AdminCreateUserResponse {
  id: number;
  email: string;
  role: UserRole;
  status: UserStatus;
  display_name: string;
  position: string | null;
  employee_no: string | null;
  joined_at: string | null;
  department_id: string | null;
}

export interface AdminUserListItem {
  id: number;
  email: string;
  role: UserRole;
  status: UserStatus;
  display_name: string | null;
  position: string | null;
  department_names: string[];
  created_at: string | null;
}

export interface AdminUserListResponse {
  items: AdminUserListItem[];
  total: number;
}

export interface AdminUserListParams {
  status?: UserStatus;
  q?: string;
  limit?: number;
  offset?: number;
}
