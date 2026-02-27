// ============================================
// API Response Types
// ============================================

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: ApiError;
  meta?: ApiMeta;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, string[]>;
}

export interface ApiMeta {
  page?: number;
  limit?: number;
  total?: number;
  totalPages?: number;
}

export interface PaginationQuery {
  page?: number;
  limit?: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

// ============================================
// Notification Types
// ============================================

export interface Notification {
  id: string;
  userId: string;
  type: NotificationType;
  title: string;
  message: string;
  data?: Record<string, unknown>;
  read: boolean;
  createdAt: string;
}

export enum NotificationType {
  PURCHASE = 'PURCHASE',
  REVIEW = 'REVIEW',
  SYSTEM = 'SYSTEM',
  EXECUTION = 'EXECUTION',
  COMMUNITY_COMMENT = 'COMMUNITY_COMMENT',
  COMMUNITY_REPLY = 'COMMUNITY_REPLY',
  COMMUNITY_UPVOTE = 'COMMUNITY_UPVOTE',
  COMMUNITY_DOWNVOTE = 'COMMUNITY_DOWNVOTE',
  CREDIT_EARNED = 'CREDIT_EARNED',
  CREDIT_SPENT = 'CREDIT_SPENT',
}

// ============================================
// Settings Types
// ============================================

export interface UserSettings {
  llmConfigs: SavedLLMConfig[];
  defaultLLMConfigId?: string;
  theme: 'dark' | 'light';
  notifications: NotificationSettings;
  execution: ExecutionPreferences;
}

export interface SavedLLMConfig {
  id: string;
  name: string;
  provider: string;
  model: string;
  apiKey: string;
  baseUrl?: string;
  isDefault: boolean;
}

export interface NotificationSettings {
  email: boolean;
  browser: boolean;
  executionComplete: boolean;
  newReview: boolean;
  sale: boolean;
}

export interface ExecutionPreferences {
  defaultTimeout: number;
  screenshotInterval: number;
  sandboxMode: boolean;
  autoSaveResults: boolean;
}
