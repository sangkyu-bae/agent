export type UserStatus = 'pending' | 'approved' | 'rejected';
export type UserRole = 'user' | 'admin';

export interface User {
  id: number;
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
