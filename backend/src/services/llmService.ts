import prisma from '../models';
import { config } from '../config';
import { NotFoundError, BadRequestError, ForbiddenError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { encrypt, decrypt } from '../utils/crypto';

// LLM Provider configurations
const LLM_MODELS: Record<string, { name: string; models: { id: string; name: string; contextWindow: number }[] }> = {
  OGENT: {
    name: 'ogent-1.0 (Platform)',
    models: [
      { id: 'ogent-1.0', name: 'ogent-1.0', contextWindow: 256000 },
    ],
  },
  OPENAI: {
    name: 'OpenAI',
    models: [
      { id: 'gpt-5', name: 'GPT-5', contextWindow: 256000 },
      { id: 'gpt-5-mini', name: 'GPT-5 Mini', contextWindow: 256000 },
      { id: 'gpt-5.2', name: 'GPT-5.2', contextWindow: 256000 },
      { id: 'gpt-4.1', name: 'GPT-4.1', contextWindow: 1047576 },
      { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini', contextWindow: 1047576 },
      { id: 'gpt-4.1-nano', name: 'GPT-4.1 Nano', contextWindow: 1047576 },
      { id: 'gpt-4o', name: 'GPT-4o', contextWindow: 128000 },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini', contextWindow: 128000 },
      { id: 'o3', name: 'o3', contextWindow: 200000 },
      { id: 'o3-mini', name: 'o3 Mini', contextWindow: 200000 },
      { id: 'o4-mini', name: 'o4 Mini', contextWindow: 200000 },
      { id: 'o1', name: 'o1', contextWindow: 200000 },
      { id: 'o1-mini', name: 'o1 Mini', contextWindow: 128000 },
      { id: 'o1-pro', name: 'o1 Pro', contextWindow: 200000 },
    ],
  },
  ANTHROPIC: {
    name: 'Anthropic',
    models: [
      { id: 'claude-opus-4-20250514', name: 'Claude Opus 4', contextWindow: 200000 },
      { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4', contextWindow: 200000 },
      { id: 'claude-3-5-sonnet-20241022', name: 'Claude 3.5 Sonnet', contextWindow: 200000 },
      { id: 'claude-3-5-haiku-20241022', name: 'Claude 3.5 Haiku', contextWindow: 200000 },
    ],
  },
  GOOGLE: {
    name: 'Google AI',
    models: [
      { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', contextWindow: 1048576 },
      { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', contextWindow: 1048576 },
      { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash', contextWindow: 1048576 },
      { id: 'gemini-1.5-pro', name: 'Gemini 1.5 Pro', contextWindow: 2097152 },
    ],
  },
  MISTRAL: {
    name: 'Mistral AI',
    models: [
      { id: 'mistral-large-latest', name: 'Mistral Large', contextWindow: 128000 },
      { id: 'mistral-medium-latest', name: 'Mistral Medium', contextWindow: 32000 },
      { id: 'mistral-small-latest', name: 'Mistral Small', contextWindow: 32000 },
      { id: 'codestral-latest', name: 'Codestral', contextWindow: 32000 },
    ],
  },
  LOCAL: {
    name: 'Local (Ollama/LM Studio)',
    models: [
      { id: 'llama3.1', name: 'Llama 3.1', contextWindow: 128000 },
      { id: 'codellama', name: 'Code Llama', contextWindow: 16384 },
      { id: 'mixtral', name: 'Mixtral 8x7B', contextWindow: 32768 },
    ],
  },
  CUSTOM: {
    name: 'Custom (OpenAI-compatible)',
    models: [
      { id: 'custom', name: 'Custom Model', contextWindow: 128000 },
    ],
  },
};

export class LLMService {
  getAvailableProviders() {
    return Object.entries(LLM_MODELS).map(([key, value]) => ({
      id: key,
      name: value.name,
      models: value.models,
    }));
  }

  getModelsForProvider(provider: string) {
    const providerConfig = LLM_MODELS[provider.toUpperCase()];
    if (!providerConfig) throw new NotFoundError('LLM Provider');
    return providerConfig.models;
  }

  async saveConfig(userId: string, data: {
    name?: string;
    provider: string;
    model: string;
    apiKey?: string;
    baseUrl?: string;
    isDefault?: boolean;
  }) {
    const isOgent = data.provider === 'OGENT';
    const configName = data.name || (isOgent ? 'ogent-1.0 (Platform Managed)' : `${data.provider} - ${data.model}`);

    let encryptedKey: string;
    try {
      // ogent-1.0 uses platform keys — no user API key needed
      encryptedKey = isOgent ? encrypt('__OGENT_PLATFORM__') : (data.apiKey ? encrypt(data.apiKey) : encrypt('none'));
    } catch (encryptError: any) {
      logger.error('Encryption failed during saveConfig', { error: encryptError.message });
      throw new BadRequestError(`Failed to encrypt API key: ${encryptError.message}`);
    }

    if (data.isDefault) {
      await prisma.lLMConfig.updateMany({
        where: { userId },
        data: { isDefault: false },
      });
    }

    const llmConfig = await prisma.lLMConfig.create({
      data: {
        userId,
        name: configName,
        provider: data.provider,
        model: data.model,
        apiKey: encryptedKey,
        baseUrl: data.baseUrl || null,
        isDefault: data.isDefault || false,
      },
    });

    if (data.isDefault) {
      await prisma.userSettings.upsert({
        where: { userId },
        create: { userId, defaultLLMConfigId: llmConfig.id },
        update: { defaultLLMConfigId: llmConfig.id },
      });
    }

    return {
      ...llmConfig,
      apiKey: data.apiKey ? '***' + data.apiKey.slice(-4) : '***none',
    };
  }

  async getUserConfigs(userId: string) {
    const configs = await prisma.lLMConfig.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
    });

    return configs.map((c) => ({
      ...c,
      apiKey: '***' + decrypt(c.apiKey).slice(-4),
    }));
  }

  async getConfig(configId: string, userId: string) {
    const llmConfig = await prisma.lLMConfig.findUnique({ where: { id: configId } });
    if (!llmConfig || llmConfig.userId !== userId) throw new NotFoundError('LLM Config');
    return llmConfig;
  }

  async getDecryptedConfig(configId: string, userId: string) {
    const llmConfig = await this.getConfig(configId, userId);
    return {
      ...llmConfig,
      apiKey: decrypt(llmConfig.apiKey),
    };
  }

  async updateConfig(configId: string, userId: string, data: Partial<{
    name: string;
    provider: string;
    model: string;
    apiKey: string;
    baseUrl: string;
    isDefault: boolean;
  }>) {
    const llmConfig = await prisma.lLMConfig.findUnique({ where: { id: configId } });
    if (!llmConfig || llmConfig.userId !== userId) throw new NotFoundError('LLM Config');

    const updateData: any = {};
    if (data.name) updateData.name = data.name;
    if (data.provider) updateData.provider = data.provider;
    if (data.model) updateData.model = data.model;
    if (data.apiKey) updateData.apiKey = encrypt(data.apiKey);
    if (data.baseUrl !== undefined) updateData.baseUrl = data.baseUrl || null;

    if (data.isDefault) {
      await prisma.lLMConfig.updateMany({ where: { userId }, data: { isDefault: false } });
      updateData.isDefault = true;
      await prisma.userSettings.upsert({
        where: { userId },
        create: { userId, defaultLLMConfigId: configId },
        update: { defaultLLMConfigId: configId },
      });
    }

    const updated = await prisma.lLMConfig.update({
      where: { id: configId },
      data: updateData,
    });

    return {
      ...updated,
      apiKey: '***' + (data.apiKey || decrypt(llmConfig.apiKey)).slice(-4),
    };
  }

  async deleteConfig(configId: string, userId: string) {
    const llmConfig = await prisma.lLMConfig.findUnique({ where: { id: configId } });
    if (!llmConfig || llmConfig.userId !== userId) throw new NotFoundError('LLM Config');

    await prisma.lLMConfig.delete({ where: { id: configId } });

    const settings = await prisma.userSettings.findUnique({ where: { userId } });
    if (settings?.defaultLLMConfigId === configId) {
      const firstConfig = await prisma.lLMConfig.findFirst({
        where: { userId },
        orderBy: { createdAt: 'asc' },
      });
      await prisma.userSettings.update({
        where: { userId },
        data: { defaultLLMConfigId: firstConfig?.id || null },
      });
    }

    logger.info(`LLM config deleted: ${configId} by user ${userId}`);
  }

  async testConfig(configId: string, userId: string): Promise<{ success: boolean; message: string; latency?: number }> {
    const llmConfig = await this.getDecryptedConfig(configId, userId);

    const start = Date.now();

    try {
      let response: any;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      const provider = llmConfig.provider.toUpperCase();

      if (provider === 'ANTHROPIC') {
        headers['x-api-key'] = llmConfig.apiKey;
        headers['anthropic-version'] = '2023-06-01';
        response = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model: llmConfig.model,
            max_tokens: 5,
            messages: [{ role: 'user', content: 'Say "OK"' }],
          }),
        });
      } else if (provider === 'GOOGLE') {
        response = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${llmConfig.model}:generateContent?key=${llmConfig.apiKey}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              contents: [{ parts: [{ text: 'Say "OK"' }] }],
              generationConfig: { maxOutputTokens: 5 },
            }),
          }
        );
      } else {
        // OpenAI, Mistral, Local, Custom, and any other provider — all use OpenAI-compatible API
        let baseUrl = llmConfig.baseUrl || '';
        if (!baseUrl) {
          if (provider === 'OPENAI') baseUrl = 'https://api.openai.com';
          else if (provider === 'MISTRAL') baseUrl = 'https://api.mistral.ai';
          else if (provider === 'LOCAL') baseUrl = 'http://localhost:11434';
          else baseUrl = 'https://api.openai.com'; // fallback
        }
        if (llmConfig.apiKey && llmConfig.apiKey !== 'none') {
          headers['Authorization'] = `Bearer ${llmConfig.apiKey}`;
        }
        // Reasoning/thinking models need different parameters
        const testModelLower = llmConfig.model.toLowerCase();
        const isTestReasoningModel = [
          'o1', 'o3', 'o4-mini', 'o4',
          'gpt-5', 'gpt-5-mini', 'gpt-5.2',
        ].some(p => testModelLower.startsWith(p) || testModelLower === p);
        const testUsesMaxCompletionTokens = isTestReasoningModel || testModelLower.startsWith('gpt-4.1');

        const testBody: Record<string, any> = {
          model: llmConfig.model,
          messages: [{
            role: isTestReasoningModel ? 'user' : 'user',
            content: 'Say "OK"',
          }],
          ...(testUsesMaxCompletionTokens
            ? { max_completion_tokens: 1024 }
            : { max_tokens: 5 }),
        };

        response = await fetch(`${baseUrl}/v1/chat/completions`, {
          method: 'POST',
          headers,
          body: JSON.stringify(testBody),
        });
      }

      const latency = Date.now() - start;

      if (response.ok) {
        return { success: true, message: 'Connection successful', latency };
      } else {
        const errorBody = await response.text();
        return { success: false, message: `API error: ${response.status} - ${errorBody}` };
      }
    } catch (error: any) {
      return { success: false, message: `Connection failed: ${error.message}` };
    }
  }
}

export const llmService = new LLMService();
