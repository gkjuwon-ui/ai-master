/**
 * ogent-1.0 Token-Based Credit Service
 * 
 * Handles per-token credit deduction for the ogent-1.0 platform model.
 * Users pay credits proportional to actual token usage, with a 1.4x markup.
 * 
 * Model routing:
 *   Execute tasks → GPT-5.2 (OpenAI, platform key)
 *   Idle/social   → llama-3.3-70b / llama-3.1-8b / gemma2-9b (Groq, platform key)
 * 
 * SECURITY: Platform API keys are NEVER sent to the frontend.
 *           Only the backend resolves ogent-1.0 → actual provider + key.
 */

import prisma from '../models';
import { config } from '../config';
import { logger } from '../utils/logger';
import { BadRequestError } from '../middleware/errorHandler';
import { exchangeService } from './exchangeService';

const PROFIT_MARKUP = 1.4;

interface ModelCost {
  modelId: string;
  provider: 'openai' | 'groq';
  inputCostPer1M: number;
  outputCostPer1M: number;
  contextWindow: number;
  supportsVision: boolean;
}

const EXECUTE_MODEL: ModelCost = {
  modelId: 'gpt-5.2',
  provider: 'openai',
  inputCostPer1M: 2.50,
  outputCostPer1M: 10.00,
  contextWindow: 256000,
  supportsVision: true,
};

const IDLE_MODELS: ModelCost[] = [
  {
    modelId: 'llama-3.3-70b-versatile',
    provider: 'groq',
    inputCostPer1M: 0.59,
    outputCostPer1M: 0.79,
    contextWindow: 128000,
    supportsVision: false,
  },
  {
    modelId: 'llama-3.1-8b-instant',
    provider: 'groq',
    inputCostPer1M: 0.05,
    outputCostPer1M: 0.08,
    contextWindow: 131072,
    supportsVision: false,
  },
  {
    modelId: 'gemma2-9b-it',
    provider: 'groq',
    inputCostPer1M: 0.20,
    outputCostPer1M: 0.20,
    contextWindow: 8192,
    supportsVision: false,
  },
];

export type OgentMode = 'execute' | 'idle';

export class OgentTokenService {
  isEnabled(): boolean {
    return config.ogent.enabled;
  }

  getModelForMode(mode: OgentMode): ModelCost {
    return mode === 'execute' ? EXECUTE_MODEL : IDLE_MODELS[0];
  }

  /**
   * Resolve ogent-1.0 to actual provider config (with platform API key).
   * SECURITY: This is the ONLY place where platform keys are injected.
   */
  resolveOgentConfig(mode: OgentMode): {
    provider: string;
    model: string;
    apiKey: string;
    baseUrl: string;
  } {
    if (!this.isEnabled()) {
      throw new BadRequestError('ogent-1.0 is not configured on this server');
    }

    if (mode === 'execute') {
      return {
        provider: 'OPENAI',
        model: EXECUTE_MODEL.modelId,
        apiKey: config.ogent.openaiApiKey,
        baseUrl: '',
      };
    }

    const idleModel = IDLE_MODELS[0];
    return {
      provider: 'CUSTOM',
      model: idleModel.modelId,
      apiKey: config.ogent.groqApiKey,
      baseUrl: 'https://api.groq.com/openai/v1',
    };
  }

  /**
   * Calculate the credit cost for a given token usage.
   * Returns the breakdown + credit amount to deduct.
   */
  calculateTokenCost(
    mode: OgentMode,
    inputTokens: number,
    outputTokens: number,
    exchangeRate: number = 10,
  ) {
    const model = this.getModelForMode(mode);
    const rawInputCost = (inputTokens / 1_000_000) * model.inputCostPer1M;
    const rawOutputCost = (outputTokens / 1_000_000) * model.outputCostPer1M;
    const rawCostUsd = rawInputCost + rawOutputCost;
    const markedUpUsd = rawCostUsd * PROFIT_MARKUP;
    const creditCharge = Math.max(0.01, Math.round(markedUpUsd * exchangeRate * 100) / 100);

    return {
      modelId: model.modelId,
      provider: model.provider,
      inputTokens,
      outputTokens,
      rawCostUsd: Math.round(rawCostUsd * 1_000_000) / 1_000_000,
      markup: PROFIT_MARKUP,
      markedUpUsd: Math.round(markedUpUsd * 1_000_000) / 1_000_000,
      exchangeRate,
      creditCharge,
    };
  }

  /**
   * Deduct credits from user based on token usage (called after each LLM call).
   * Fails gracefully — logs error but doesn't crash execution.
   */
  async deductTokenCredits(
    userId: string,
    mode: OgentMode,
    inputTokens: number,
    outputTokens: number,
    sessionId?: string,
  ): Promise<{ success: boolean; charged: number; remaining: number }> {
    try {
      const rateInfo = await exchangeService.getExchangeRate();
      const cost = this.calculateTokenCost(mode, inputTokens, outputTokens, rateInfo.rate);

      if (cost.creditCharge <= 0) {
        return { success: true, charged: 0, remaining: 0 };
      }

      const user = await prisma.user.findUnique({
        where: { id: userId },
        select: { credits: true },
      });

      if (!user || user.credits < cost.creditCharge) {
        logger.warn(
          `ogent-1.0 insufficient credits: user=${userId} need=${cost.creditCharge} have=${user?.credits ?? 0}`
        );
        return { success: false, charged: 0, remaining: user?.credits ?? 0 };
      }

      const result = await prisma.$transaction(async (tx) => {
        const updated = await tx.user.update({
          where: { id: userId },
          data: { credits: { decrement: cost.creditCharge } },
          select: { credits: true },
        });

        await tx.creditLedger.create({
          data: {
            userId,
            amount: -cost.creditCharge,
            reason: 'OGENT_TOKEN_USAGE',
            referenceId: sessionId || null,
            balance: updated.credits,
          },
        });

        return updated.credits;
      });

      logger.debug(
        `ogent-1.0 token charge: user=${userId} model=${cost.modelId} ` +
        `in=${inputTokens} out=${outputTokens} raw=$${cost.rawCostUsd} ` +
        `charged=${cost.creditCharge}cr remaining=${result}cr`
      );

      return { success: true, charged: cost.creditCharge, remaining: result };
    } catch (err: any) {
      logger.error(`ogent-1.0 credit deduction failed: ${err.message}`);
      return { success: false, charged: 0, remaining: 0 };
    }
  }

  /**
   * Pre-check if user has enough credits for an estimated ogent-1.0 usage.
   */
  async canAfford(
    userId: string,
    mode: OgentMode,
    estimatedInputTokens: number = 4000,
    estimatedOutputTokens: number = 1000,
  ): Promise<{ canAfford: boolean; estimatedCost: number; balance: number }> {
    const rateInfo = await exchangeService.getExchangeRate();
    const cost = this.calculateTokenCost(mode, estimatedInputTokens, estimatedOutputTokens, rateInfo.rate);

    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { credits: true },
    });
    const balance = user?.credits ?? 0;

    return {
      canAfford: balance >= cost.creditCharge,
      estimatedCost: cost.creditCharge,
      balance,
    };
  }

  /** Get pricing info for UI display. */
  getPricingInfo() {
    return {
      markup: PROFIT_MARKUP,
      executeModel: {
        modelId: EXECUTE_MODEL.modelId,
        provider: EXECUTE_MODEL.provider,
        inputPer1M: EXECUTE_MODEL.inputCostPer1M,
        outputPer1M: EXECUTE_MODEL.outputCostPer1M,
        inputPer1MWithMarkup: Math.round(EXECUTE_MODEL.inputCostPer1M * PROFIT_MARKUP * 100) / 100,
        outputPer1MWithMarkup: Math.round(EXECUTE_MODEL.outputCostPer1M * PROFIT_MARKUP * 100) / 100,
      },
      idleModels: IDLE_MODELS.map(m => ({
        modelId: m.modelId,
        provider: m.provider,
        inputPer1M: m.inputCostPer1M,
        outputPer1M: m.outputCostPer1M,
        inputPer1MWithMarkup: Math.round(m.inputCostPer1M * PROFIT_MARKUP * 100) / 100,
        outputPer1MWithMarkup: Math.round(m.outputCostPer1M * PROFIT_MARKUP * 100) / 100,
      })),
    };
  }
}

export const ogentTokenService = new OgentTokenService();
