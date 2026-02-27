/**
 * SDK Types - Shared type definitions for agent development.
 */

export interface AgentManifestConfig {
  name: string;
  slug: string;
  version: string;
  description: string;
  shortDescription?: string;
  category: AgentCategory;
  capabilities: AgentCapability[];
  pricingModel: PricingModel;
  price: number;
  tags?: string[];
  entrypoint: string;
  runtime: 'python' | 'node';
  minRuntimeVersion?: string;
  configSchema?: ConfigSchemaField[];
  screenshots?: string[];
  icon?: string;
  repository?: string;
  documentation?: string;
}

export type AgentCategory =
  | 'CODING' | 'DESIGN' | 'RESEARCH' | 'DATA_ANALYSIS'
  | 'WRITING' | 'AUTOMATION' | 'COMMUNICATION' | 'PRODUCTIVITY'
  | 'MEDIA' | 'MONITORING' | 'SYSTEM' | 'OTHER';

export type AgentCapability =
  | 'MOUSE_CONTROL' | 'KEYBOARD_INPUT' | 'SCREEN_CAPTURE' | 'SCREENSHOT_ANALYSIS'
  | 'APP_MANAGEMENT' | 'FILE_SYSTEM' | 'BROWSER_CONTROL'
  | 'CLIPBOARD' | 'SYSTEM_COMMANDS' | 'WINDOW_MANAGEMENT'
  | 'AUDIO_CONTROL' | 'NETWORK';

export type PricingModel = 'FREE' | 'ONE_TIME' | 'SUBSCRIPTION_MONTHLY' | 'SUBSCRIPTION_YEARLY' | 'PAY_PER_USE';

export interface ConfigSchemaField {
  key: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select';
  required?: boolean;
  default?: any;
  options?: { value: string; label: string }[];
  description?: string;
}

export interface SDKConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
}

export interface UploadResult {
  success: boolean;
  agentId?: string;
  version?: string;
  message: string;
  errors?: string[];
}

export interface ValidateResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface TestResult {
  passed: boolean;
  totalTests: number;
  passedTests: number;
  failedTests: number;
  errors: string[];
  warnings: string[];
  duration: number;
  tests?: {
    name: string;
    passed: boolean;
    message?: string;
    duration: number;
  }[];
  totalDuration?: number;
}

export interface PublishOptions {
  draft?: boolean;
  changelog?: string;
  releaseNotes?: string;
  listed?: boolean;
}

export interface AgentStats {
  downloads: number;
  rating: number;
  reviewCount: number;
  earnings: number;
  activeUsers: number;
}

export interface OSAction {
  type: string;
  params: Record<string, any>;
}

export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMResponse {
  content: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
}
