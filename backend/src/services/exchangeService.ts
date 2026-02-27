/**
 * Exchange Service — Credit ↔ Money Exchange System
 * 
 * Users can buy credits with real money or sell credits for real money.
 * Platform earns revenue by taking asymmetric fees on exchanges.
 * 
 * Exchange rate is calculated based on THREE factors:
 * 1. Demand pressure — buy/sell volume ratio in last 24h (±20%)
 * 2. Supply inflation — total circulating credits vs per-user baseline (up to +50%)
 * 3. Issuance velocity — credits minted in last 24h vs expected baseline (up to +20%)
 * 
 * This ensures that when lots of credits are minted (signups, subscriptions),
 * the rate increases → agents cost more credits → economy stays balanced.
 * 
 * Platform fees (ASYMMETRIC — discourages cash-out arbitrage):
 * - BUY:  5% fee (encourage credit purchase)
 * - SELL: 20% fee (discourage cash-out, platform revenue)
 * 
 * Additional sell protections:
 * - Daily sell limit: 500 credits/day per user
 * - Minimum sell: 100 credits per transaction
 * - Minimum balance: must keep 50 credits after selling
 */

import prisma from '../models';
import { BadRequestError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { creditService } from './creditService';

// ── Exchange Configuration ──────────────────────────────────────

const EXCHANGE_CONFIG = {
  /** Base exchange rate: how many credits per $1 */
  baseRate: 10,          // 1 credit = $0.10, so $1 = 10 credits

  /** Platform fee percentage — ASYMMETRIC to discourage arbitrage */
  buyFeeRate: 0.05,      // 5% fee on buying credits (encourage inflow)
  sellFeeRate: 0.20,     // 20% fee on selling credits (discourage cash-out)

  /** Minimum exchange amounts */
  minBuyCredits: 5,      // Minimum 5 credits ($0.50)
  minSellCredits: 100,   // Minimum 100 credits to sell ($10.00)

  /** Maximum exchange amounts per transaction */
  maxBuyCredits: 10000,  // Max 10,000 credits per buy ($1,000)
  maxSellCredits: 500,   // Max 500 credits per sell per transaction

  /** Daily sell limit per user */
  dailySellLimit: 500,   // Max 500 credits sold per day per user

  /** Minimum balance after selling — users must keep skin in the game */
  minBalanceAfterSell: 50,

  /** Dynamic rate adjustment window (ms) - 24 hours */
  rateWindowMs: 24 * 60 * 60 * 1000,

  /** Max rate deviation from demand pressure (±20%) */
  maxRateDeviation: 0.20,

  /** Max rate increase from supply inflation (+50%) */
  maxSupplyDeviation: 0.50,

  /** Max rate increase from issuance velocity (+20%) */
  maxIssuanceDeviation: 0.20,

  /** Per-user baseline for "healthy" credit supply */
  supplyBaselinePerUser: 100,

  /** Minimum supply baseline (prevents division by tiny numbers) */
  supplyBaselineFloor: 1000,

  /** Expected daily credit issuance per user (for velocity calc) */
  dailyIssuancePerUser: 5,

  /** Minimum daily issuance baseline */
  dailyIssuanceFloor: 50,

  /** Absolute min/max rate bounds (rate can range from 5 to 30 cr/$1) */
  absoluteMinRate: 5,
  absoluteMaxRate: 30,
};

export class ExchangeService {
  /**
   * Get current exchange rate (credits per $1)
   * Adjusts based on recent buy/sell volume
   */
  async getExchangeRate(): Promise<{
    rate: number;       // credits per $1
    creditPrice: number; // $ per credit
    buyFeeRate: number;  // buy fee %
    sellFeeRate: number; // sell fee %
    buyExample: { credits: number; cost: number; fee: number; total: number };
    sellExample: { credits: number; payout: number; fee: number; net: number };
    dailySellLimit: number;
    minBalanceAfterSell: number;
  }> {
    const rate = await this._calculateRate();
    const creditPrice = 1 / rate;

    // Example: buying 100 credits
    const buyCost = 100 / rate;
    const buyFee = buyCost * EXCHANGE_CONFIG.buyFeeRate;
    const buyTotal = buyCost + buyFee;

    // Example: selling 100 credits
    const sellPayout = 100 / rate;
    const sellFee = sellPayout * EXCHANGE_CONFIG.sellFeeRate;
    const sellNet = sellPayout - sellFee;

    return {
      rate,
      creditPrice: Math.round(creditPrice * 10000) / 10000,
      buyFeeRate: EXCHANGE_CONFIG.buyFeeRate,
      sellFeeRate: EXCHANGE_CONFIG.sellFeeRate,
      buyExample: {
        credits: 100,
        cost: Math.round(buyCost * 100) / 100,
        fee: Math.round(buyFee * 100) / 100,
        total: Math.round(buyTotal * 100) / 100,
      },
      sellExample: {
        credits: 100,
        payout: Math.round(sellPayout * 100) / 100,
        fee: Math.round(sellFee * 100) / 100,
        net: Math.round(sellNet * 100) / 100,
      },
      dailySellLimit: EXCHANGE_CONFIG.dailySellLimit,
      minBalanceAfterSell: EXCHANGE_CONFIG.minBalanceAfterSell,
    };
  }

  /**
   * Buy credits with real money
   * User pays money → receives credits (platform takes fee from money)
   */
  async buyCredits(userId: string, creditAmount: number): Promise<{
    exchangeId: string;
    creditsReceived: number;
    moneyPaid: number;
    fee: number;
    exchangeRate: number;
    newBalance: number;
  }> {
    if (creditAmount < EXCHANGE_CONFIG.minBuyCredits) {
      throw new BadRequestError(`Minimum purchase is ${EXCHANGE_CONFIG.minBuyCredits} credits`);
    }
    if (creditAmount > EXCHANGE_CONFIG.maxBuyCredits) {
      throw new BadRequestError(`Maximum purchase is ${EXCHANGE_CONFIG.maxBuyCredits} credits per transaction`);
    }

    const rate = await this._calculateRate();
    const baseCost = creditAmount / rate;    // Money cost before fee
    const fee = baseCost * EXCHANGE_CONFIG.buyFeeRate;
    const totalCost = baseCost + fee;        // User pays this

    // Create exchange record and credit the user
    const result = await prisma.$transaction(async (tx) => {
      // Grant credits to user
      const user = await tx.user.update({
        where: { id: userId },
        data: { credits: { increment: creditAmount } },
        select: { credits: true },
      });

      // Record in credit ledger
      await tx.creditLedger.create({
        data: {
          userId,
          amount: creditAmount,
          reason: 'EXCHANGE_BUY',
          referenceId: null, // will update after exchange record created
          balance: user.credits,
        },
      });

      // Create exchange record
      const exchange = await tx.creditExchange.create({
        data: {
          userId,
          type: 'BUY',
          creditAmount,
          moneyAmount: Math.round(baseCost * 100) / 100,
          exchangeRate: rate,
          fee: Math.round(fee * 100) / 100,
          feeRate: EXCHANGE_CONFIG.buyFeeRate,
          netMoney: Math.round(totalCost * 100) / 100,
          status: 'COMPLETED',
        },
      });

      return { exchange, newBalance: user.credits };
    });

    logger.info(`Exchange BUY: user=${userId} credits=${creditAmount} cost=$${Math.round(totalCost * 100) / 100} fee=$${Math.round(fee * 100) / 100} rate=${rate}`);

    return {
      exchangeId: result.exchange.id,
      creditsReceived: creditAmount,
      moneyPaid: Math.round(totalCost * 100) / 100,
      fee: Math.round(fee * 100) / 100,
      exchangeRate: rate,
      newBalance: result.newBalance,
    };
  }

  /**
   * Sell credits for real money
   * User gives credits → receives money (platform takes 20% fee from payout)
   * Additional protections: daily limit, minimum balance requirement
   */
  async sellCredits(userId: string, creditAmount: number): Promise<{
    exchangeId: string;
    creditsSold: number;
    moneyReceived: number;
    fee: number;
    exchangeRate: number;
    newBalance: number;
  }> {
    if (creditAmount < EXCHANGE_CONFIG.minSellCredits) {
      throw new BadRequestError(`Minimum sell amount is ${EXCHANGE_CONFIG.minSellCredits} credits`);
    }
    if (creditAmount > EXCHANGE_CONFIG.maxSellCredits) {
      throw new BadRequestError(`Maximum sell amount per transaction is ${EXCHANGE_CONFIG.maxSellCredits} credits`);
    }

    // Check balance
    const balance = await creditService.getBalance(userId);
    if (balance < creditAmount) {
      throw new BadRequestError(`Insufficient credits. Balance: ${balance}, attempted: ${creditAmount}`);
    }

    // Minimum balance after sell — users must keep skin in the game
    const balanceAfterSell = balance - creditAmount;
    if (balanceAfterSell < EXCHANGE_CONFIG.minBalanceAfterSell) {
      throw new BadRequestError(
        `You must maintain at least ${EXCHANGE_CONFIG.minBalanceAfterSell} credits after selling. ` +
        `Current balance: ${balance}, max sellable: ${Math.max(0, balance - EXCHANGE_CONFIG.minBalanceAfterSell)} credits`
      );
    }

    // Daily sell limit — prevent mass cash-out
    const dayStart = new Date();
    dayStart.setHours(0, 0, 0, 0);
    const todaySold = await prisma.creditExchange.aggregate({
      where: {
        userId,
        type: 'SELL',
        status: 'COMPLETED',
        createdAt: { gte: dayStart },
      },
      _sum: { creditAmount: true },
    });
    const alreadySold = todaySold._sum.creditAmount ?? 0;
    if (alreadySold + creditAmount > EXCHANGE_CONFIG.dailySellLimit) {
      const remaining = Math.max(0, EXCHANGE_CONFIG.dailySellLimit - alreadySold);
      throw new BadRequestError(
        `Daily sell limit of ${EXCHANGE_CONFIG.dailySellLimit} credits exceeded. ` +
        `Already sold ${alreadySold} credits today. Remaining limit: ${remaining} credits`
      );
    }

    const rate = await this._calculateRate();
    const grossPayout = creditAmount / rate;    // Payout before fee
    const fee = grossPayout * EXCHANGE_CONFIG.sellFeeRate;  // 20% fee
    const netPayout = grossPayout - fee;        // User receives this

    // Deduct credits and create exchange record
    const result = await prisma.$transaction(async (tx) => {
      // Deduct credits from user
      const user = await tx.user.update({
        where: { id: userId },
        data: { credits: { decrement: creditAmount } },
        select: { credits: true },
      });

      // Record in credit ledger
      await tx.creditLedger.create({
        data: {
          userId,
          amount: -creditAmount,
          reason: 'EXCHANGE_SELL',
          referenceId: null,
          balance: user.credits,
        },
      });

      // Create exchange record
      const exchange = await tx.creditExchange.create({
        data: {
          userId,
          type: 'SELL',
          creditAmount,
          moneyAmount: Math.round(grossPayout * 100) / 100,
          exchangeRate: rate,
          fee: Math.round(fee * 100) / 100,
          feeRate: EXCHANGE_CONFIG.sellFeeRate,
          netMoney: Math.round(netPayout * 100) / 100,
          status: 'COMPLETED',
        },
      });

      return { exchange, newBalance: user.credits };
    });

    logger.info(`Exchange SELL: user=${userId} credits=${creditAmount} payout=$${Math.round(netPayout * 100) / 100} fee=$${Math.round(fee * 100) / 100} (${EXCHANGE_CONFIG.sellFeeRate * 100}%) rate=${rate}`);

    return {
      exchangeId: result.exchange.id,
      creditsSold: creditAmount,
      moneyReceived: Math.round(netPayout * 100) / 100,
      fee: Math.round(fee * 100) / 100,
      exchangeRate: rate,
      newBalance: result.newBalance,
    };
  }

  /** Get exchange history for a user */
  async getHistory(userId: string, options: { page?: number; limit?: number } = {}) {
    const { page = 1, limit = 20 } = options;
    const skip = (page - 1) * limit;

    const [exchanges, total] = await Promise.all([
      prisma.creditExchange.findMany({
        where: { userId },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.creditExchange.count({ where: { userId } }),
    ]);

    return {
      exchanges,
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    };
  }

  /** Get platform-wide exchange stats (admin use) */
  async getExchangeStats() {
    const [totalBuys, totalSells, totalFees] = await Promise.all([
      prisma.creditExchange.aggregate({
        where: { type: 'BUY', status: 'COMPLETED' },
        _sum: { creditAmount: true, moneyAmount: true, fee: true },
        _count: true,
      }),
      prisma.creditExchange.aggregate({
        where: { type: 'SELL', status: 'COMPLETED' },
        _sum: { creditAmount: true, moneyAmount: true, fee: true },
        _count: true,
      }),
      prisma.creditExchange.aggregate({
        where: { status: 'COMPLETED' },
        _sum: { fee: true },
      }),
    ]);

    return {
      buys: {
        count: totalBuys._count,
        totalCredits: totalBuys._sum.creditAmount ?? 0,
        totalMoney: totalBuys._sum.moneyAmount ?? 0,
        totalFees: totalBuys._sum.fee ?? 0,
      },
      sells: {
        count: totalSells._count,
        totalCredits: totalSells._sum.creditAmount ?? 0,
        totalMoney: totalSells._sum.moneyAmount ?? 0,
        totalFees: totalSells._sum.fee ?? 0,
      },
      platformRevenue: totalFees._sum.fee ?? 0,
      currentRate: await this._calculateRate(),
    };
  }

  /**
   * Calculate dynamic exchange rate based on THREE factors:
   * 
   * 1. DEMAND PRESSURE (existing) — buy/sell volume ratio in 24h window
   *    More buying → rate ↓ (credits cost more dollars)
   *    More selling → rate ↑ (credits cost less dollars)
   *    Range: ±20% of base rate
   * 
   * 2. SUPPLY INFLATION (new) — total circulating credits vs per-user baseline
   *    More credits in circulation → rate ↑ (credits worth less, need more for agents)
   *    Uses log₂ scale to prevent extreme spikes
   *    Range: 0% to +50%
   * 
   * 3. ISSUANCE VELOCITY (new) — credits minted in last 24h vs expected rate
   *    Lots of upvotes/signups/drips → rate ↑ (short-term inflation signal)
   *    Uses log₂ scale
   *    Range: 0% to +20%
   * 
   * Final rate is clamped to [5, 30] credits per $1.
   */
  private async _calculateRate(): Promise<number> {
    const windowStart = new Date(Date.now() - EXCHANGE_CONFIG.rateWindowMs);

    const [buyVolume, sellVolume, subDripVolume, totalCirculating, userCount, recentIssuance] = await Promise.all([
      // Exchange buy volume (24h)
      prisma.creditExchange.aggregate({
        where: { type: 'BUY', status: 'COMPLETED', createdAt: { gte: windowStart } },
        _sum: { creditAmount: true },
      }),
      // Exchange sell volume (24h)
      prisma.creditExchange.aggregate({
        where: { type: 'SELL', status: 'COMPLETED', createdAt: { gte: windowStart } },
        _sum: { creditAmount: true },
      }),
      // Subscription drips = cash → credits, counts as buy pressure
      prisma.creditLedger.aggregate({
        where: { reason: 'SUBSCRIPTION_DRIP', createdAt: { gte: windowStart } },
        _sum: { amount: true },
      }),
      // Total circulating credit supply (all user balances)
      prisma.user.aggregate({
        _sum: { credits: true },
      }),
      // Total user count (for per-capita baseline)
      prisma.user.count(),
      // Recent credit minting events (24h) — upvotes, signups, drips
      prisma.creditLedger.aggregate({
        where: {
          reason: { in: ['SIGNUP_BONUS', 'UPVOTE', 'SUBSCRIPTION_DRIP'] },
          amount: { gt: 0 },
          createdAt: { gte: windowStart },
        },
        _sum: { amount: true },
      }),
    ]);

    // ── Factor 1: Demand pressure (±20%) ──
    const bought = (buyVolume._sum.creditAmount ?? 0) + (subDripVolume._sum.amount ?? 0);
    const sold = sellVolume._sum.creditAmount ?? 0;
    const totalVolume = bought + sold;

    let demandDeviation = 0;
    if (totalVolume > 0) {
      const buyPressure = (bought - sold) / totalVolume; // -1 to +1
      demandDeviation = buyPressure * EXCHANGE_CONFIG.maxRateDeviation;
    }

    // ── Factor 2: Supply inflation (0% to +50%) ──
    // Compare total circulating credits to a per-user baseline
    const circulating = totalCirculating._sum.credits ?? 0;
    const users = Math.max(userCount, 1);
    const baselineSupply = Math.max(
      users * EXCHANGE_CONFIG.supplyBaselinePerUser,
      EXCHANGE_CONFIG.supplyBaselineFloor
    );

    // supplyRatio: 1.0 = healthy, 2.0 = 2× inflation, 8.0 = 8× inflation
    const supplyRatio = Math.max(1, circulating / baselineSupply);
    // Log₂ scale: log₂(1)=0, log₂(2)=1, log₂(4)=2, log₂(8)=3
    const supplyInflation = Math.log2(supplyRatio);
    // Each log₂ unit = +15% rate increase, capped at maxSupplyDeviation
    const supplyDeviation = Math.min(
      supplyInflation * 0.15,
      EXCHANGE_CONFIG.maxSupplyDeviation
    );

    // ── Factor 3: Issuance velocity (0% to +20%) ──
    // How fast are credits being minted right now vs expected daily rate?
    const issued = recentIssuance._sum.amount ?? 0;
    const issuanceBaseline = Math.max(
      users * EXCHANGE_CONFIG.dailyIssuancePerUser,
      EXCHANGE_CONFIG.dailyIssuanceFloor
    );

    const issuanceRatio = Math.max(1, issued / issuanceBaseline);
    const issuanceInflation = Math.log2(issuanceRatio);
    const issuanceDeviation = Math.min(
      issuanceInflation * 0.10,
      EXCHANGE_CONFIG.maxIssuanceDeviation
    );

    // ── Combine all factors ──
    // demand: buy pressure → rate ↓ (credits cost more $)
    // supply + issuance: inflation → rate ↑ (credits worth less, agents cost more credits)
    const adjustedRate = EXCHANGE_CONFIG.baseRate * (1 - demandDeviation + supplyDeviation + issuanceDeviation);

    // Clamp to absolute bounds
    const finalRate = Math.max(
      EXCHANGE_CONFIG.absoluteMinRate,
      Math.min(EXCHANGE_CONFIG.absoluteMaxRate, adjustedRate)
    );

    logger.debug(`Exchange rate calc: demand=${demandDeviation.toFixed(3)} supply=${supplyDeviation.toFixed(3)} issuance=${issuanceDeviation.toFixed(3)} → rate=${finalRate.toFixed(2)} (circulating=${circulating} users=${users} issued24h=${issued})`);

    return Math.round(finalRate * 100) / 100;
  }
}

export const exchangeService = new ExchangeService();
