// ============================================
// Execution Types
// ============================================

export interface ExecutionSession {
  id: string;
  userId: string;
  name: string;
  status: ExecutionStatus;
  agents: ExecutionAgent[];
  prompt: string;
  config: ExecutionConfig;
  logs: ExecutionLog[];
  result?: ExecutionResult;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
}

export interface ExecutionAgent {
  agentId: string;
  name: string;
  icon: string;
  order: number;
  status: ExecutionAgentStatus;
  config?: Record<string, unknown>;
}

export enum ExecutionStatus {
  PENDING = 'PENDING',
  RUNNING = 'RUNNING',
  PAUSED = 'PAUSED',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  CANCELLED = 'CANCELLED',
}

export enum ExecutionAgentStatus {
  QUEUED = 'QUEUED',
  INITIALIZING = 'INITIALIZING',
  RUNNING = 'RUNNING',
  WAITING_INPUT = 'WAITING_INPUT',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
}

export interface ExecutionConfig {
  llmProvider: LLMProvider;
  llmModel: string;
  llmApiKey: string;
  maxExecutionTime: number;
  screenshotInterval: number;
  allowedCapabilities: string[];
  sandboxMode: boolean;
}

export enum LLMProvider {
  OPENAI = 'OPENAI',
  ANTHROPIC = 'ANTHROPIC',
  GOOGLE = 'GOOGLE',
  MISTRAL = 'MISTRAL',
  LOCAL = 'LOCAL',
  CUSTOM = 'CUSTOM',
}

export interface LLMConfig {
  provider: LLMProvider;
  model: string;
  apiKey: string;
  baseUrl?: string;
  maxTokens?: number;
  temperature?: number;
}

export interface LLMModelInfo {
  provider: LLMProvider;
  models: {
    id: string;
    name: string;
    description: string;
    contextWindow: number;
    pricing?: {
      input: number;
      output: number;
    };
  }[];
}

export interface ExecutionLog {
  id: string;
  sessionId: string;
  agentId: string;
  timestamp: string;
  level: LogLevel;
  type: LogType;
  message: string;
  data?: Record<string, unknown>;
  screenshot?: string;
}

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
}

export enum LogType {
  SYSTEM = 'SYSTEM',
  AGENT = 'AGENT',
  LLM = 'LLM',
  OS_ACTION = 'OS_ACTION',
  SCREENSHOT = 'SCREENSHOT',
  USER_INPUT = 'USER_INPUT',
}

export interface ExecutionResult {
  success: boolean;
  summary: string;
  artifacts: ExecutionArtifact[];
  screenshots: string[];
  totalTime: number;
  tokensUsed: number;
  cost: number;
}

export interface ExecutionArtifact {
  name: string;
  type: string;
  path?: string;
  url?: string;
  size: number;
}

export interface ExecutionCommand {
  type: 'start' | 'pause' | 'resume' | 'cancel' | 'input';
  sessionId: string;
  data?: Record<string, unknown>;
}

// WebSocket Events
export enum WSEventType {
  // Client -> Server
  START_EXECUTION = 'start_execution',
  PAUSE_EXECUTION = 'pause_execution',
  RESUME_EXECUTION = 'resume_execution',
  CANCEL_EXECUTION = 'cancel_execution',
  USER_INPUT = 'user_input',

  // Server -> Client
  EXECUTION_STARTED = 'execution_started',
  EXECUTION_LOG = 'execution_log',
  EXECUTION_SCREENSHOT = 'execution_screenshot',
  EXECUTION_STATUS = 'execution_status',
  EXECUTION_COMPLETED = 'execution_completed',
  EXECUTION_ERROR = 'execution_error',
  AGENT_STATUS_CHANGE = 'agent_status_change',
  INPUT_REQUIRED = 'input_required',
}

export interface WSMessage {
  event: WSEventType;
  data: Record<string, unknown>;
  timestamp: string;
}
