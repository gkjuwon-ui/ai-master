// @ts-ignore
import dotenv from 'dotenv';
import path from 'path';
import fs from 'fs';

// Try multiple paths to find .env file
const possiblePaths = [
  path.resolve(__dirname, '../../.env'), // Development (src/config -> ../../.env)
  path.resolve(__dirname, '../.env'),     // Build in backend root
  path.resolve(process.cwd(), '.env'),    // Current working directory
  path.resolve(process.cwd(), '../.env'),
];

for (const envPath of possiblePaths) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
    console.log(`[Config] Loaded .env from: ${envPath}`);
    break;
  }
}

const env = process.env.NODE_ENV || 'development';
const isProduction = env === 'production';

// Fail fast if critical secrets are missing in production
if (isProduction) {
  if (!process.env.JWT_SECRET || process.env.JWT_SECRET === 'dev-secret-change-me') {
    throw new Error('FATAL: JWT_SECRET must be set in production. Refusing to start with dev defaults.');
  }
  if (!process.env.JWT_REFRESH_SECRET || process.env.JWT_REFRESH_SECRET === 'dev-refresh-secret-change-me') {
    throw new Error('FATAL: JWT_REFRESH_SECRET must be set in production. Refusing to start with dev defaults.');
  }
}

export const config = {
  env,
  port: parseInt(process.env.PORT || '4000', 10),
  frontendUrl: process.env.FRONTEND_URL || 'http://localhost:3000',
  backendUrl: process.env.BACKEND_URL || 'http://localhost:4000',

  jwt: {
    secret: process.env.JWT_SECRET || 'dev-secret-change-me',
    refreshSecret: process.env.JWT_REFRESH_SECRET || 'dev-refresh-secret-change-me',
    expiresIn: process.env.JWT_EXPIRES_IN || '15m',
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || '7d',
  },

  agentRuntime: {
    url: process.env.AGENT_RUNTIME_URL || 'http://127.0.0.1:5000',
    secret: process.env.AGENT_RUNTIME_SECRET || 'agent-runtime-secret',
    maxExecutionTime: parseInt(process.env.AGENT_MAX_EXECUTION_TIME || '600000', 10),
    screenshotInterval: parseInt(process.env.AGENT_SCREENSHOT_INTERVAL || '1000', 10),
  },

  redis: {
    url: process.env.REDIS_URL || 'redis://localhost:6379',
  },

  upload: {
    dir: process.env.UPLOAD_DIR || './uploads',
    maxSize: process.env.MAX_UPLOAD_SIZE || '50mb',
  },

  logging: {
    level: process.env.LOG_LEVEL || 'debug',
    dir: process.env.LOG_DIR || './logs',
  },

  rateLimit: {
    windowMs: parseInt(process.env.RATE_LIMIT_WINDOW || '60000', 10), // 1분
    max: parseInt(process.env.RATE_LIMIT_MAX || '1000', 10), // 1분당 1000개 요청
  },

  cors: {
    origins: (process.env.CORS_ORIGINS || 'http://localhost:3000').split(','),
  },

  smtp: {
    host: process.env.SMTP_HOST || 'smtp.gmail.com',
    port: parseInt(process.env.SMTP_PORT || '587', 10),
    secure: process.env.SMTP_SECURE === 'true',
    user: process.env.SMTP_USER || '',
    pass: process.env.SMTP_PASS || '',
    from: process.env.SMTP_FROM || process.env.SMTP_USER || 'noreply@ogenti.com',
  },

  stripe: {
    secretKey: process.env.STRIPE_SECRET_KEY || '',
    publishableKey: process.env.STRIPE_PUBLISHABLE_KEY || '',
    webhookSecret: process.env.STRIPE_WEBHOOK_SECRET || '',
    enabled: !!process.env.STRIPE_SECRET_KEY,
  },

  ogent: {
    openaiApiKey: process.env.OGENT_OPENAI_API_KEY || '',
    groqApiKey: process.env.OGENT_GROQ_API_KEY || '',
    enabled: !!(process.env.OGENT_OPENAI_API_KEY && process.env.OGENT_GROQ_API_KEY),
  },
} as const;

export type Config = typeof config;
