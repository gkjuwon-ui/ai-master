/**
 * Credit Service — Ogenti Credits System
 * 
 * Replaces Stripe-based cash payments with an internal credit system.
 * 
 * Credit sources:
 * - Signup bonus: +5 credits (reduced from 20 — anti-abuse)
 * - Agent sale: 85% of credit cost goes to developer (15% platform commission)
 * - Exchange buy: purchase credits with real money
 * - Subscription payout: credits from subscription usage-time settlement
 * 
 * Credit sinks:
 * - Agent purchase: costs credits based on agent price tier
 * - Exchange sell: sell credits for real money (20% fee)
 * - Agent transfer: 10% platform fee on agent-to-agent tips
 * 
 * Upvotes/downvotes NO LONGER affect credits — they are reputation only.
 */

import prisma from '../models';
import { BadRequestError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { exchangeService } from './exchangeService';

// ── Economy Configuration ──────────────────────────────────

/** Platform commission on agent sales (15% — developer gets 85%) */
const AGENT_SALE_COMMISSION = 0.15;

/** Platform fee on agent-to-agent transfers (10%) */
const TRANSFER_FEE_RATE = 0.10;

/** Maximum transfer per transaction */
const MAX_TRANSFER_AMOUNT = 50;

/** Signup bonus credits */
const SIGNUP_BONUS_AMOUNT = 5;

export class CreditService {
  /** Get user's current credit balance */
  async getBalance(userId: string): Promise<number> {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { credits: true },
    });
    return user?.credits ?? 0;
  }

  /** Get credit transaction history */
  async getLedger(userId: string, options: { page?: number; limit?: number } = {}) {
    const { page = 1, limit = 20 } = options;
    const skip = (page - 1) * limit;

    const [entries, total] = await Promise.all([
      prisma.creditLedger.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.creditLedger.count({ where: { userId } }),
    ]);

    return {
      entries,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    };
  }

  /** Adjust credits and record in ledger (internal use) */
  async adjustCredits(userId: string, amount: number, reason: string, referenceId?: string) {
    // Use transaction to ensure atomicity
    const result = await prisma.$transaction(async (tx) => {
      const user = await tx.user.update({
        where: { id: userId },
        data: { credits: { increment: amount } },
        select: { credits: true },
      });

      await tx.creditLedger.create({
        data: {
          userId,
          amount,
          reason,
          referenceId: referenceId || null,
          balance: user.credits,
        },
      });

      return user.credits;
    });

    logger.info(`Credits adjusted: user=${userId} amount=${amount} reason=${reason} newBalance=${result}`);
    return result;
  }

  /** Grant signup bonus */
  async grantSignupBonus(userId: string) {
    const existing = await prisma.creditLedger.findFirst({
      where: { userId, reason: 'SIGNUP_BONUS' },
    });
    if (existing) return; // Already granted

    await this.adjustCredits(userId, SIGNUP_BONUS_AMOUNT, 'SIGNUP_BONUS');
    logger.info(`Signup bonus granted: user=${userId} +${SIGNUP_BONUS_AMOUNT} credits`);
  }

  /** Purchase an agent with credits — Platform takes 15% commission, developer gets 85% */
  async purchaseAgent(userId: string, agentId: string) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new BadRequestError('Agent not found');

    // Can't purchase your own agent
    if (agent.developerId === userId) {
      throw new BadRequestError('You cannot purchase your own agent');
    }

    // Check if already purchased
    const existing = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId, agentId } },
    });
    if (existing && existing.status === 'COMPLETED') {
      throw new BadRequestError('Agent already purchased');
    }

    // Calculate credit cost from agent price tier (dynamic: price × exchange rate)
    const creditCost = await this.getCreditCost(agent.price, agent.tier);

    if (creditCost > 0) {
      const balance = await this.getBalance(userId);
      if (balance < creditCost) {
        throw new BadRequestError(`Not enough credits. Need ${creditCost}, have ${balance}. Earn more by posting valuable content in the community!`);
      }
    }

    // Deduct from buyer, credit 85% to developer (15% platform commission), and create purchase
    await prisma.$transaction(async (tx) => {
      if (creditCost > 0) {
        // Deduct credits from buyer (full price)
        const buyer = await tx.user.update({
          where: { id: userId },
          data: { credits: { decrement: creditCost } },
          select: { credits: true },
        });

        await tx.creditLedger.create({
          data: {
            userId,
            amount: -creditCost,
            reason: 'AGENT_PURCHASE',
            referenceId: agentId,
            balance: buyer.credits,
          },
        });

        // Credit 85% to developer (15% platform commission burned)
        const developerShare = Math.round(creditCost * (1 - AGENT_SALE_COMMISSION));
        const platformFee = creditCost - developerShare;
        
        const developer = await tx.user.update({
          where: { id: agent.developerId },
          data: { credits: { increment: developerShare } },
          select: { credits: true },
        });

        await tx.creditLedger.create({
          data: {
            userId: agent.developerId,
            amount: developerShare,
            reason: 'AGENT_SALE',
            referenceId: agentId,
            balance: developer.credits,
          },
        });

        logger.info(`Agent sale commission: total=${creditCost} developer=${developerShare} (${Math.round((1 - AGENT_SALE_COMMISSION) * 100)}%) platform=${platformFee} (${Math.round(AGENT_SALE_COMMISSION * 100)}%)`);
      }

      await tx.purchase.upsert({
        where: { userId_agentId: { userId, agentId } },
        create: {
          userId,
          agentId,
          creditCost,
          status: 'COMPLETED',
        },
        update: {
          creditCost,
          status: 'COMPLETED',
        },
      });

      // Increment download count
      await tx.agent.update({
        where: { id: agentId },
        data: { downloads: { increment: 1 } },
      });
    });

    logger.info(`Agent purchased: user=${userId} agent=${agentId} cost=${creditCost} credits → developer=${agent.developerId} receives ${Math.round(creditCost * (1 - AGENT_SALE_COMMISSION))} credits (${Math.round((1 - AGENT_SALE_COMMISSION) * 100)}%, platform takes ${Math.round(AGENT_SALE_COMMISSION * 100)}%)`);

    // Auto-create social profile for the purchased agent
    try {
      const { socialService } = require('./socialService');
      const purchase = await prisma.purchase.findUnique({
        where: { userId_agentId: { userId, agentId } },
        select: { id: true },
      });
      if (purchase) {
        await socialService.createProfile(purchase.id, userId, agentId);
        logger.info(`Social profile auto-created for purchase ${purchase.id}`);
      }
    } catch (err: any) {
      // Non-critical: don't fail purchase if profile creation fails
      logger.warn(`Social profile creation failed (non-critical): ${err.message}`);
    }

    return {
      success: true,
      agentId,
      creditCost,
      remaining: await this.getBalance(userId),
    };
  }

  /** Map agent price/tier to credit cost — dynamic: dollarPrice × exchangeRate */
  async getCreditCost(price: number, tier: string): Promise<number> {
    if (price === 0 || tier === 'F') return 0;

    // Get current exchange rate (credits per $1)
    const rateInfo = await exchangeService.getExchangeRate();
    const rate = rateInfo.rate; // e.g. 10 credits/$1

    // Credit cost = dollar price × rate
    return Math.max(1, Math.round(price * rate));
  }

  /** Sync version for display only (uses base rate) — never for transactions */
  getCreditCostSync(price: number, tier: string): number {
    if (price === 0 || tier === 'F') return 0;
    // Use base rate of 10 cr/$1 for quick estimates
    return Math.max(1, Math.round(price * 10));
  }

  /** Get credit summary for a user (for dashboard) */
  async getCreditSummary(userId: string) {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: { credits: true },
    });

    // Get recent transactions
    const recentTransactions = await prisma.creditLedger.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
      take: 10,
    });

    // Calculate total earned/spent
    const stats = await prisma.creditLedger.groupBy({
      by: ['reason'],
      where: { userId },
      _sum: { amount: true },
      _count: true,
    });

    const earned = stats
      .filter(s => (s._sum.amount ?? 0) > 0)
      .reduce((sum, s) => sum + (s._sum.amount ?? 0), 0);
    const spent = Math.abs(stats
      .filter(s => (s._sum.amount ?? 0) < 0)
      .reduce((sum, s) => sum + (s._sum.amount ?? 0), 0));

    return {
      balance: user?.credits ?? 0,
      totalEarned: earned,
      totalSpent: spent,
      recentTransactions,
      breakdown: stats.map(s => ({
        reason: s.reason,
        total: s._sum.amount ?? 0,
        count: s._count,
      })),
    };
  }

  // ── Agent-to-Agent Credit Transfer ──

  /** Transfer credits from one agent's owner to another agent's owner (10% platform fee) */
  async transferCredits(
    ownerId: string,
    fromAgentId: string,
    fromAgentName: string,
    toAgentId: string,
    toAgentName: string,
    amount: number,
    reason: string,
    postId?: string,
    commentId?: string,
    messageId?: string,
    toOwnerId?: string,
  ) {
    if (amount <= 0) throw new BadRequestError('Transfer amount must be positive');
    if (amount > MAX_TRANSFER_AMOUNT) throw new BadRequestError(`Maximum transfer is ${MAX_TRANSFER_AMOUNT} credits per transaction`);

    // Check balance
    const balance = await this.getBalance(ownerId);
    if (balance < amount) {
      throw new BadRequestError(`Not enough credits. Have ${balance}, need ${amount}`);
    }

    // Find the receiving agent's owner.
    // Priority: (1) explicitly provided toOwnerId, (2) AgentProfile.ownerId for the active profile,
    // (3) fall back to Agent.developerId (original marketplace creator).
    let receiverOwnerId: string;
    if (toOwnerId) {
      receiverOwnerId = toOwnerId;
      // Verify the target agent exists
      const targetAgent = await prisma.agent.findUnique({ where: { id: toAgentId }, select: { id: true } });
      if (!targetAgent) throw new BadRequestError('Target agent not found');
    } else {
      const activeProfile = await prisma.agentProfile.findFirst({
        where: { baseAgentId: toAgentId, isActive: true },
        select: { ownerId: true },
      });
      if (activeProfile) {
        receiverOwnerId = activeProfile.ownerId;
      } else {
        const targetAgent = await prisma.agent.findUnique({
          where: { id: toAgentId },
          select: { developerId: true },
        });
        if (!targetAgent) throw new BadRequestError('Target agent not found');
        receiverOwnerId = targetAgent.developerId;
      }
    }

    // Calculate 10% platform fee (burned from circulation)
    const platformFee = Math.max(1, Math.round(amount * TRANSFER_FEE_RATE));
    const receiverAmount = amount - platformFee;

    // Execute transfer atomically
    const result = await prisma.$transaction(async (tx: any) => {
      // Deduct full amount from sender
      const sender = await tx.user.update({
        where: { id: ownerId },
        data: { credits: { decrement: amount } },
        select: { credits: true },
      });
      await tx.creditLedger.create({
        data: {
          userId: ownerId,
          amount: -amount,
          reason: 'AGENT_TRANSFER_SENT',
          referenceId: toAgentId,
          balance: sender.credits,
        },
      });

      // Credit reduced amount to receiver (after 10% fee)
      const receiver = await tx.user.update({
        where: { id: receiverOwnerId },
        data: { credits: { increment: receiverAmount } },
        select: { credits: true },
      });
      await tx.creditLedger.create({
        data: {
          userId: receiverOwnerId,
          amount: receiverAmount,
          reason: 'AGENT_TRANSFER_RECEIVED',
          referenceId: fromAgentId,
          balance: receiver.credits,
        },
      });

      // Update recipient agent's totalCreditsEarned (per-agent visible stat)
      await tx.agentProfile.updateMany({
        where: { baseAgentId: toAgentId, isActive: true },
        data: { totalCreditsEarned: { increment: receiverAmount } },
      });

      // Record the transfer
      const transfer = await tx.agentCreditTransfer.create({
        data: {
          fromAgentId,
          fromAgentName,
          toAgentId,
          toAgentName,
          amount,
          reason,
          postId: postId || null,
          commentId: commentId || null,
          messageId: messageId || null,
          ownerId,
        },
      });

      return { transfer, newBalance: sender.credits };
    });

    logger.info(`Agent transfer: ${fromAgentName} -> ${toAgentName} sent=${amount} received=${receiverAmount} fee=${platformFee} (${Math.round(TRANSFER_FEE_RATE * 100)}%). Reason: ${reason}`);
    return result;
  }

  // ── Agent Purchase Requests ──

  /** Agent requests permission to buy another agent */
  async createPurchaseRequest(
    requestingAgentId: string,
    requestingAgentName: string,
    targetAgentSlug: string,
    reason: string,
    ownerId: string,
  ) {
    // Find target agent
    const target = await prisma.agent.findUnique({
      where: { slug: targetAgentSlug },
      select: { id: true, name: true, slug: true, tier: true, price: true, developerId: true },
    });
    if (!target) throw new BadRequestError(`Agent '${targetAgentSlug}' not found`);

    // Can't buy own agent
    if (target.developerId === ownerId) {
      throw new BadRequestError('Cannot request purchase of your own agent');
    }

    // Already purchased?
    const existing = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId: ownerId, agentId: target.id } },
    });
    if (existing && existing.status === 'COMPLETED') {
      throw new BadRequestError('Agent already purchased');
    }

    // Check for duplicate pending request
    const pendingRequest = await prisma.agentPurchaseRequest.findFirst({
      where: {
        requestingAgentId,
        targetAgentId: target.id,
        ownerId,
        status: 'PENDING',
      },
    });
    if (pendingRequest) {
      throw new BadRequestError('A purchase request is already pending for this agent');
    }

    const creditCost = await this.getCreditCost(target.price, target.tier);

    const request = await prisma.agentPurchaseRequest.create({
      data: {
        requestingAgentId,
        requestingAgentName,
        targetAgentId: target.id,
        targetAgentName: target.name,
        targetAgentSlug: target.slug,
        creditCost,
        ownerId,
        reason,
      },
    });

    // Create a notification for the owner
    await prisma.notification.create({
      data: {
        userId: ownerId,
        type: 'AGENT_PURCHASE_REQUEST',
        title: `${requestingAgentName} wants to buy an agent!`,
        message: `Your agent "${requestingAgentName}" wants to purchase "${target.name}" for ${creditCost} credits. Reason: ${reason}`,
        data: JSON.stringify({
          requestId: request.id,
          requestingAgentId,
          requestingAgentName,
          targetAgentId: target.id,
          targetAgentName: target.name,
          creditCost,
        }),
      },
    });

    logger.info(`Purchase request: ${requestingAgentName} wants ${target.name} (${creditCost} credits)`);
    return request;
  }

  /** Get pending purchase requests for an owner */
  async getPurchaseRequests(ownerId: string) {
    return prisma.agentPurchaseRequest.findMany({
      where: { ownerId },
      orderBy: { createdAt: 'desc' },
    });
  }

  /** Owner approves a purchase request */
  async approvePurchaseRequest(requestId: string, ownerId: string) {
    const request = await prisma.agentPurchaseRequest.findUnique({
      where: { id: requestId },
    });
    if (!request) throw new BadRequestError('Request not found');
    if (request.ownerId !== ownerId) throw new BadRequestError('Not your request');
    if (request.status !== 'PENDING') throw new BadRequestError(`Request already ${request.status.toLowerCase()}`);

    // Check balance
    const balance = await this.getBalance(ownerId);
    if (balance < request.creditCost) {
      throw new BadRequestError(`Not enough credits. Need ${request.creditCost}, have ${balance}`);
    }

    // Execute the purchase
    const purchaseResult = await this.purchaseAgent(ownerId, request.targetAgentId);

    // Update request status
    await prisma.agentPurchaseRequest.update({
      where: { id: requestId },
      data: { status: 'APPROVED', respondedAt: new Date() },
    });

    logger.info(`Purchase request approved: ${request.requestingAgentName} got ${request.targetAgentName}`);
    return purchaseResult;
  }

  /** Owner rejects a purchase request */
  async rejectPurchaseRequest(requestId: string, ownerId: string) {
    const request = await prisma.agentPurchaseRequest.findUnique({
      where: { id: requestId },
    });
    if (!request) throw new BadRequestError('Request not found');
    if (request.ownerId !== ownerId) throw new BadRequestError('Not your request');
    if (request.status !== 'PENDING') throw new BadRequestError(`Request already ${request.status.toLowerCase()}`);

    await prisma.agentPurchaseRequest.update({
      where: { id: requestId },
      data: { status: 'REJECTED', respondedAt: new Date() },
    });

    logger.info(`Purchase request rejected: ${request.requestingAgentName} denied ${request.targetAgentName}`);
    return { success: true };
  }
}

export const creditService = new CreditService();