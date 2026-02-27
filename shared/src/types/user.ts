// ============================================
// User & Authentication Types
// ============================================

export interface User {
  id: string;
  email: string;
  username: string;
  displayName: string;
  avatar?: string;
  role: UserRole;
  credits: number;
  createdAt: string;
  updatedAt: string;
}

export enum UserRole {
  USER = 'USER',
  DEVELOPER = 'DEVELOPER',
  ADMIN = 'ADMIN',
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  displayName: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}
