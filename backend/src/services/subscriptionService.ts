/**
 * Subscription Service — Daily Credit Drip Model (Fixed Credits, Dynamic USD)
 * 
 * Business model:
 * - Subscription tiers provide FIXED daily/monthly credit amounts
 * - The USD price FLOATS based on the current credit exchange rate
 * - USD price = (monthlyCredits / exchangeRate) × (1 + SUBSCRIPTION_PREMIUM)
 * - A 25% convenience premium is applied vs direct exchange to keep the
 *   credit exchange competitive (exchange has 5% fee but lower unit cost)
 * - Subscription drips count as buy volume, affecting the exchange rate
 * - Developers earn 100% from agent purchases (no platform fee)
 * - Platform earns revenue from subscriptions + exchange fees
 * 
 * Fixed Credit Amounts:
 * - STARTER: 5 cr/day  (150/mo)
 * - PRO:     12 cr/day (360/mo)
 * - APEX:    25 cr/day (750/mo)
 * 
 * USD price is dynamic: (monthlyCredits / exchangeRate) × 1.25
 * At base rate (10 cr/$1):
 * - STARTER: (150/10)×1.25 = $18.75/mo
 * - PRO:     (360/10)×1.25 = $45.00/mo
 * - APEX:    (750/10)×1.25 = $93.75/mo
 */

import prisma from '../models';
import { BadRequestError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { exchangeService } from './exchangeService';

// ── Subscription Configuration ──────────────────────────────────

export const SUBSCRIPTION_TIERS = {
  STARTER: {
    name: 'Starter',
    dailyCredits: 5,
    monthlyCredits: 150,
    description: 'Daily credits — Run B-tier agents or save for bigger ones',
    perks: ['Daily credit drip', 'Price tracks exchange rate', 'Includes convenience premium', 'Cancel anytime'],
    color: '#60A5FA',
  },
  PRO: {
    name: 'Pro',
    dailyCredits: 12,
    monthlyCredits: 360,
    description: 'Daily credits — Run A-tier agents daily with room to spare',
    perks: ['Daily credit drip', 'Price tracks exchange rate', 'Includes convenience premium', 'Cancel anytime'],
    color: '#A78BFA',
  },
  APEX: {
    name: 'Apex',
    dailyCredits: 25,
    monthlyCredits: 750,
    description: 'Daily credits — Run any agent every day, even S+',
    perks: ['Daily credit drip', 'Price tracks exchange rate', 'Includes convenience premium'],
    color: '#F59E0B',
  },
} as const;

export type SubscriptionTierKey = keyof typeof SUBSCRIPTION_TIERS;

/** Minimum hours between drips (prevents abuse) */
const DRIP_INTERVAL_MS = 20 * 60 * 60 * 1000; // 20 hours (slightly less than 24h for timezone flexibility)

/**
 * Convenience premium on subscription pricing vs direct exchange.
 * Subscriptions offer predictability & daily drip but cost more per credit
 * so the credit exchange (5% fee, lower unit cost) stays competitive.
 */
const SUBSCRIPTION_PREMIUM = 0.25; // 25%

/** Calculate dynamic USD price for a tier based on current exchange rate + premium */
function getDynamicPriceUsd(monthlyCredits: number, rate: number): number {
  return Math.round((monthlyCredits / rate) * (1 + SUBSCRIPTION_PREMIUM) * 100) / 100;
}

export class SubscriptionService {
  /** Get available subscription tiers with fixed credits and dynamic USD price */
  async getTiers() {
    const rateInfo = await exchangeService.getExchangeRate();
    const rate = rateInfo.rate;

    return Object.entries(SUBSCRIPTION_TIERS).map(([key, tier]) => {
      const priceUsd = getDynamicPriceUsd(tier.monthlyCredits, rate);
      return {
        id: key,
        name: tier.name,
        priceUsd,
        dailyCredits: tier.dailyCredits,
        monthlyCredits: tier.monthlyCredits,
        description: tier.description,
        perks: [
          `${tier.dailyCredits} credits daily`,
          `~${tier.monthlyCredits} credits/month`,
          ...tier.perks,
        ],
        color: tier.color,
        exchangeRate: rate,
      };
    });
  }

  /** Get user's active subscription (if any) */
  async getSubscription(userId: string) {
    const sub = await prisma.subscription.findFirst({
      where: { userId, status: { in: ['ACTIVE', 'CANCELLED'] } },
      orderBy: { createdAt: 'desc' },
    });

    if (!sub) return null;

    // Check if expired
    if (sub.currentPeriodEnd < new Date() && sub.status === 'ACTIVE') {
      // Auto-expire
      await prisma.subscription.update({
        where: { id: sub.id },
        data: { status: 'EXPIRED' },
      });
      return null;
    }

    // Don't show cancelled subs past their period end
    if (sub.status === 'CANCELLED' && sub.currentPeriodEnd < new Date()) {
      return null;
    }

    const tierInfo = SUBSCRIPTION_TIERS[sub.tier as SubscriptionTierKey];

    // If tier is invalid/unknown, auto-expire and return null so the UI is unblocked
    if (!tierInfo) {
      await prisma.subscription.update({
        where: { id: sub.id },
        data: { status: 'EXPIRED' },
      });
      return null;
    }

    const canDrip = this._canDrip(sub.lastDripAt);

    // Calculate current dynamic USD price
    let currentPriceUsd = sub.priceUsd;
    try {
      const rateInfo = await exchangeService.getExchangeRate();
      currentPriceUsd = getDynamicPriceUsd(tierInfo.monthlyCredits, rateInfo.rate);
    } catch {}

    return {
      ...sub,
      priceUsd: currentPriceUsd,
      dailyCredits: tierInfo.dailyCredits,
      tierInfo,
      canClaimToday: canDrip,
      daysRemaining: Math.max(0, Math.ceil((sub.currentPeriodEnd.getTime() - Date.now()) / (1000 * 60 * 60 * 24))),
    };
  }

  /** Subscribe to a tier (creates new subscription) */
  async subscribe(userId: string, tier: string): Promise<any> {
    const tierKey = tier.toUpperCase() as SubscriptionTierKey;
    const tierInfo = SUBSCRIPTION_TIERS[tierKey];
    if (!tierInfo) {
      throw new BadRequestError(`Invalid subscription tier: ${tier}. Valid tiers: ${Object.keys(SUBSCRIPTION_TIERS).join(', ')}`);
    }

    // Check for existing active subscription (only block if the tier is valid)
    const existing = await prisma.subscription.findFirst({
      where: { userId, status: 'ACTIVE' },
    });
    if (existing) {
      const existingTierInfo = SUBSCRIPTION_TIERS[existing.tier as SubscriptionTierKey];
      if (existingTierInfo) {
        throw new BadRequestError('You already have an active subscription. Cancel it first or upgrade.');
      }
      // Existing subscription has an invalid tier — auto-expire it and allow re-subscribe
      await prisma.subscription.update({
        where: { id: existing.id },
        data: { status: 'EXPIRED' },
      });
    }

    const now = new Date();
    const periodEnd = new Date(now);
    periodEnd.setMonth(periodEnd.getMonth() + 1);

    // Calculate dynamic USD price at subscription time
    let priceUsd: number;
    try {
      const rateInfo = await exchangeService.getExchangeRate();
      priceUsd = getDynamicPriceUsd(tierInfo.monthlyCredits, rateInfo.rate);
    } catch {
      priceUsd = getDynamicPriceUsd(tierInfo.monthlyCredits, 10); // Fallback to base rate
    }

    const subscription = await prisma.subscription.create({
      data: {
        userId,
        tier: tierKey,
        status: 'ACTIVE',
        priceUsd,
        dailyCredits: tierInfo.dailyCredits,
        currentPeriodStart: now,
        currentPeriodEnd: periodEnd,
        lastDripAt: null, // Can claim immediately
      },
    });

    logger.info(`Subscription created: user=${userId} tier=${tierKey} price=$${priceUsd} fixedDailyCredits=${tierInfo.dailyCredits}`);

    return {
      ...subscription,
      dailyCredits: tierInfo.dailyCredits,
      tierInfo,
      canClaimToday: true,
    };
  }

  /** Cancel a subscription (marks as cancelled, remains active until period end) */
  async cancel(userId: string): Promise<any> {
    const sub = await prisma.subscription.findFirst({
      where: { userId, status: 'ACTIVE' },
    });
    if (!sub) {
      throw new BadRequestError('No active subscription found');
    }

    const updated = await prisma.subscription.update({
      where: { id: sub.id },
      data: {
        status: 'CANCELLED',
        cancelledAt: new Date(),
      },
    });

    logger.info(`Subscription cancelled: user=${userId} tier=${sub.tier} endsAt=${sub.currentPeriodEnd}`);

    return updated;
  }

  /** Upgrade/change subscription tier */
  async changeTier(userId: string, newTier: string): Promise<any> {
    const tierKey = newTier.toUpperCase() as SubscriptionTierKey;
    const tierInfo = SUBSCRIPTION_TIERS[tierKey];
    if (!tierInfo) {
      throw new BadRequestError(`Invalid tier: ${newTier}`);
    }

    const sub = await prisma.subscription.findFirst({
      where: { userId, status: 'ACTIVE' },
    });
    if (!sub) {
      throw new BadRequestError('No active subscription to change');
    }

    if (sub.tier === tierKey) {
      throw new BadRequestError('Already on this tier');
    }

    // Calculate dynamic USD price at change time
    let priceUsd: number;
    try {
      const rateInfo = await exchangeService.getExchangeRate();
      priceUsd = getDynamicPriceUsd(tierInfo.monthlyCredits, rateInfo.rate);
    } catch {
      priceUsd = getDynamicPriceUsd(tierInfo.monthlyCredits, 10);
    }

    const updated = await prisma.subscription.update({
      where: { id: sub.id },
      data: {
        tier: tierKey,
        priceUsd,
        dailyCredits: tierInfo.dailyCredits,
      },
    });

    logger.info(`Subscription changed: user=${userId} from=${sub.tier} to=${tierKey} fixedDailyCredits=${tierInfo.dailyCredits}`);

    return { ...updated, tierInfo };
  }

  /**
   * Apply subscription after a verified payment.
   * - No active subscription: create a new one
   * - Active subscription on different tier: switch tier
   * - Active subscription on same tier: return current subscription (idempotent)
   */
  async activateAfterPayment(userId: string, tier: string): Promise<any> {
    const tierKey = tier.toUpperCase() as SubscriptionTierKey;
    const tierInfo = SUBSCRIPTION_TIERS[tierKey];
    if (!tierInfo) {
      throw new BadRequestError(`Invalid subscription tier: ${tier}`);
    }

    const existing = await prisma.subscription.findFirst({
      where: { userId, status: 'ACTIVE' },
    });

    if (!existing) {
      return this.subscribe(userId, tierKey);
    }

    if (existing.tier === tierKey) {
      const current = await this.getSubscription(userId);
      if (current) return current;
      // If getSubscription auto-expired stale data, create a fresh one
      return this.subscribe(userId, tierKey);
    }

    return this.changeTier(userId, tierKey);
  }

  /**
   * Claim daily credits from subscription.
   * Each subscriber can claim once per ~20 hours.
   * Grants the tier's dailyCredits amount.
   */
  async claimDaily(userId: string): Promise<{
    credited: number;
    newBalance: number;
    nextClaimAt: string;
  }> {
    const sub = await prisma.subscription.findFirst({
      where: { userId, status: { in: ['ACTIVE', 'CANCELLED'] } },
      orderBy: { createdAt: 'desc' },
    });

    if (!sub) {
      throw new BadRequestError('No active subscription. Subscribe first to receive daily credits.');
    }

    // Check if subscription period is still valid
    if (sub.currentPeriodEnd < new Date()) {
      throw new BadRequestError('Subscription period has expired. Please renew.');
    }

    // Check drip cooldown
    if (!this._canDrip(sub.lastDripAt)) {
      const nextClaimAt = new Date(sub.lastDripAt!.getTime() + DRIP_INTERVAL_MS);
      throw new BadRequestError(`Already claimed today. Next claim available at ${nextClaimAt.toISOString()}`);
    }

    // Fixed daily credits from tier (not dynamic)
    const tierInfo = SUBSCRIPTION_TIERS[sub.tier as SubscriptionTierKey];
    if (!tierInfo) {
      throw new BadRequestError('Invalid subscription tier on record');
    }
    const creditsToGrant = tierInfo.dailyCredits;
    const now = new Date();

    // Grant credits atomically
    const result = await prisma.$transaction(async (tx) => {
      // Update subscription lastDripAt
      await tx.subscription.update({
        where: { id: sub.id },
        data: { lastDripAt: now },
      });

      // Grant credits
      const user = await tx.user.update({
        where: { id: userId },
        data: { credits: { increment: creditsToGrant } },
        select: { credits: true },
      });

      // Record in ledger
      await tx.creditLedger.create({
        data: {
          userId,
          amount: creditsToGrant,
          reason: 'SUBSCRIPTION_DRIP',
          referenceId: sub.id,
          balance: user.credits,
        },
      });

      return user.credits;
    });

    const nextClaimAt = new Date(now.getTime() + DRIP_INTERVAL_MS);

    logger.info(`Daily drip: user=${userId} tier=${sub.tier} credits=+${creditsToGrant} newBalance=${result}`);

    return {
      credited: creditsToGrant,
      newBalance: result,
      nextClaimAt: nextClaimAt.toISOString(),
    };
  }

  /** Check if enough time has passed since lastDripAt */
  private _canDrip(lastDripAt: Date | null): boolean {
    if (!lastDripAt) return true;
    return Date.now() - lastDripAt.getTime() >= DRIP_INTERVAL_MS;
  }
}

export const subscriptionService = new SubscriptionService();
