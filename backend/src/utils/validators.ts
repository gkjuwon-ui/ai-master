import { z } from 'zod';

export const registerSchema = z.object({
  email: z.string().email('Invalid email format'),
  username: z.string().min(3).max(30).regex(/^[a-zA-Z0-9_-]+$/, 'Username can only contain letters, numbers, hyphens, and underscores'),
  password: z.string().min(8).max(128),
  displayName: z.string().min(1).max(100),
});

export const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

export const agentCreateSchema = z.object({
  name: z.string().min(2).max(100),
  description: z.string().min(10).max(500),
  longDescription: z.string().min(10).max(10000).optional().default('No detailed description provided.'),
  category: z.enum([
    'CODING', 'DESIGN', 'RESEARCH', 'WRITING', 'DATA_ANALYSIS',
    'AUTOMATION', 'COMMUNICATION', 'PRODUCTIVITY', 'MEDIA',
    'MONITORING', 'SYSTEM', 'OTHER',
  ]),
  tags: z.array(z.string()).max(10).optional().default([]),
  capabilities: z.array(z.string()).optional().default([]),
  price: z.number().min(0).optional().default(0),
  pricingModel: z.enum(['FREE', 'ONE_TIME', 'SUBSCRIPTION_MONTHLY', 'SUBSCRIPTION_YEARLY', 'PAY_PER_USE']).optional().default('FREE'),
  runtime: z.enum(['python', 'node']).default('python'),
  entryPoint: z.string().default('main.py'),
  permissions: z.array(z.string()).optional().default([]),
  configSchema: z.any().optional(),
  inputSchema: z.any().optional(),
  outputSchema: z.any().optional(),
});

export const agentUpdateSchema = agentCreateSchema.partial();

export const agentQuerySchema = z.object({
  page: z.coerce.number().min(1).default(1),
  limit: z.coerce.number().min(1).max(10000).default(20),
  category: z.string().optional(),
  search: z.string().optional(),
  sortBy: z.enum(['popular', 'recent', 'rating', 'price_asc', 'price_desc']).default('popular'),
  pricing: z.enum(['free', 'paid']).optional(),
  priceMin: z.coerce.number().optional(),
  priceMax: z.coerce.number().optional(),
  tags: z.string().optional(), // comma-separated
});

export const reviewSchema = z.object({
  rating: z.number().min(1).max(5),
  title: z.string().max(200).optional().default('Review'),
  content: z.string().min(3).max(5000),
});

export const llmConfigSchema = z.object({
  id: z.string().optional(),
  name: z.string().max(100).optional(),
  provider: z.string().min(1),
  model: z.string().min(1),
  apiKey: z.string().optional(),
  baseUrl: z.string().url().optional().or(z.literal('')).or(z.literal(undefined)),
  isDefault: z.boolean().default(false),
});

export const executionCreateSchema = z.object({
  name: z.string().min(1).max(200).optional(),
  prompt: z.string().min(1).max(10000),
  agentIds: z.array(z.string()).min(1).max(10),
  llmConfigId: z.string(),
  config: z.object({
    maxExecutionTime: z.number().min(10000).max(1800000).default(600000),
    screenshotInterval: z.number().min(500).max(10000).default(1000),
    sandboxMode: z.boolean().default(true),
  }).optional(),
});

export const settingsUpdateSchema = z.object({
  theme: z.enum(['dark', 'light']).optional(),
  defaultLLMConfigId: z.string().optional(),
  emailNotifications: z.boolean().optional(),
  browserNotifications: z.boolean().optional(),
  executionTimeout: z.number().min(10000).optional(),
  screenshotInterval: z.number().min(500).optional(),
  sandboxMode: z.boolean().optional(),
  autoSaveResults: z.boolean().optional(),
});
