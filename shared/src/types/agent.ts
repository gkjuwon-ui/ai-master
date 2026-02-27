// ============================================
// Agent & Plugin Types
// ============================================

export interface Agent {
  id: string;
  name: string;
  slug: string;
  description: string;
  longDescription: string;
  version: string;
  icon: string;
  screenshots: string[];
  category: AgentCategory;
  tags: string[];
  capabilities: AgentCapability[];
  tier: AgentTier;
  domain: AgentDomain;
  price: number;
  currency: string;
  pricingModel: PricingModel;
  developer: AgentDeveloper;
  stats: AgentStats;
  manifest: AgentManifest;
  status: AgentStatus;
  createdAt: string;
  updatedAt: string;
}

export interface AgentDeveloper {
  id: string;
  username: string;
  displayName: string;
  avatar?: string;
  verified: boolean;
}

export interface AgentStats {
  downloads: number;
  rating: number;
  reviewCount: number;
  activeUsers: number;
}

export enum AgentCategory {
  CODING = 'CODING',
  DESIGN = 'DESIGN',
  RESEARCH = 'RESEARCH',
  WRITING = 'WRITING',
  DATA_ANALYSIS = 'DATA_ANALYSIS',
  AUTOMATION = 'AUTOMATION',
  COMMUNICATION = 'COMMUNICATION',
  PRODUCTIVITY = 'PRODUCTIVITY',
  MEDIA = 'MEDIA',
  MONITORING = 'MONITORING',
  SYSTEM = 'SYSTEM',
  OTHER = 'OTHER',
}

// ── Tier & Domain: Performance is strictly proportional to price ──

export enum AgentTier {
  F = 'F',         // Free ($0) — bare minimum utilities
  B_MINUS = 'B-',  // Budget ($0.49-$1.99) — basic single-domain
  C = 'C',         // Affordable ($2-$3.99) — decent, vision only
  B = 'B',         // Mid ($4-$7.99) — standard, vision + SoM
  A = 'A',         // Premium ($8-$12.99) — strong, + planning
  S = 'S',         // Pro ($13-$19.99) — expert, + memory
  S_PLUS = 'S+',   // Ultra ($20-$29.99) — godmode, cross-domain
}

export enum AgentDomain {
  CODING = 'coding',
  DESIGN = 'design',
  RESEARCH = 'research',
  WRITING = 'writing',
  DATA_ANALYSIS = 'data_analysis',
  AUTOMATION = 'automation',
  PRODUCTIVITY = 'productivity',
  GENERAL = 'general',
}

export enum AgentCapability {
  MOUSE_CONTROL = 'MOUSE_CONTROL',
  KEYBOARD_INPUT = 'KEYBOARD_INPUT',
  SCREENSHOT = 'SCREENSHOT',
  FILE_SYSTEM = 'FILE_SYSTEM',
  BROWSER = 'BROWSER',
  CLIPBOARD = 'CLIPBOARD',
  WINDOW_MANAGEMENT = 'WINDOW_MANAGEMENT',
  PROCESS_MANAGEMENT = 'PROCESS_MANAGEMENT',
  NETWORK = 'NETWORK',
  AUDIO = 'AUDIO',
  NOTIFICATION = 'NOTIFICATION',
}

export enum PricingModel {
  FREE = 'FREE',
  ONE_TIME = 'ONE_TIME',
  SUBSCRIPTION_MONTHLY = 'SUBSCRIPTION_MONTHLY',
  SUBSCRIPTION_YEARLY = 'SUBSCRIPTION_YEARLY',
  PAY_PER_USE = 'PAY_PER_USE',
}

export enum AgentStatus {
  DRAFT = 'DRAFT',
  PENDING_REVIEW = 'PENDING_REVIEW',
  PUBLISHED = 'PUBLISHED',
  SUSPENDED = 'SUSPENDED',
  DEPRECATED = 'DEPRECATED',
}

export interface AgentManifest {
  id: string;
  name: string;
  version: string;
  entryPoint: string;
  runtime: 'python' | 'node';
  permissions: AgentCapability[];
  dependencies: Record<string, string>;
  configSchema?: AgentConfigSchema;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

export interface AgentConfigSchema {
  type: 'object';
  properties: Record<string, {
    type: string;
    description: string;
    default?: unknown;
    enum?: unknown[];
    required?: boolean;
  }>;
}

export interface AgentReview {
  id: string;
  userId: string;
  agentId: string;
  rating: number;
  title: string;
  content: string;
  createdAt: string;
}

export interface AgentListQuery {
  page?: number;
  limit?: number;
  category?: AgentCategory;
  search?: string;
  sortBy?: 'popular' | 'recent' | 'rating' | 'price_asc' | 'price_desc';
  priceMin?: number;
  priceMax?: number;
  tags?: string[];
}

export interface AgentListResponse {
  agents: Agent[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface PurchasedAgent {
  id: string;
  agentId: string;
  agent: Agent;
  userId: string;
  purchasedAt: string;
  expiresAt?: string;
  licenseKey: string;
}
