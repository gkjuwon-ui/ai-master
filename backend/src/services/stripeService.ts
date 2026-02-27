/**
 * Stripe Service — Real Payment Integration
 * 
 * Connects the credit exchange system to actual Stripe payments.
 * When Stripe is configured (STRIPE_SECRET_KEY env var), credits
 * can be purchased with real money via Stripe Checkout.
 * 
 * When Stripe is NOT configured, the system falls back to
 * the existing credit-only exchange (no real money moves).
 */

import { config } from '../config';
import { logger } from '../utils/logger';
import { creditService } from './creditService';
import { exchangeService } from './exchangeService';
import { subscriptionService } from './subscriptionService';
import prisma from '../models';

let stripe: any = null;

function getStripe() {
  if (!stripe && config.stripe.enabled) {
    try {
      const Stripe = require('stripe');
      stripe = new Stripe(config.stripe.secretKey);
      logger.info('Stripe initialized successfully');
    } catch (e: any) {
      logger.warn(`Stripe initialization failed: ${e.message}`);
    }
  }
  return stripe;
}

export class StripeService {
  /** Check if Stripe is configured and ready */
  isEnabled(): boolean {
    return config.stripe.enabled && !!getStripe();
  }

  /** Create a Stripe Checkout session to buy credits */
  async createCheckoutSession(
    userId: string,
    creditAmount: number,
    successUrl: string,
    cancelUrl: string,
  ) {
    const stripeClient = getStripe();
    if (!stripeClient) {
      throw new Error('Stripe is not configured. Set STRIPE_SECRET_KEY in Settings.');
    }

    // Calculate price based on exchange rate
    const rateInfo = await exchangeService.getExchangeRate();
    const costUsd = creditAmount / rateInfo.rate;
    const fee = costUsd * rateInfo.buyFeeRate;
    const totalCents = Math.round((costUsd + fee) * 100);

    if (totalCents < 50) {
      throw new Error('Minimum purchase amount is $0.50');
    }

    const session = await stripeClient.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [
        {
          price_data: {
            currency: 'usd',
            product_data: {
              name: `${creditAmount} Ogenti Credits`,
              description: `Purchase ${creditAmount} credits at $${(costUsd / creditAmount).toFixed(4)}/credit`,
            },
            unit_amount: totalCents,
          },
          quantity: 1,
        },
      ],
      mode: 'payment',
      success_url: successUrl,
      cancel_url: cancelUrl,
      metadata: {
        userId,
        creditAmount: String(creditAmount),
        exchangeRate: String(rateInfo.rate),
      },
    });

    logger.info(`Stripe checkout created: user=${userId} credits=${creditAmount} amount=$${(totalCents / 100).toFixed(2)}`);

    return {
      sessionId: session.id,
      url: session.url,
      amount: totalCents / 100,
      credits: creditAmount,
    };
  }

  /** Create a PaymentIntent for in-app credit purchase (Stripe Elements) */
  async createCreditPaymentIntent(userId: string, creditAmount: number) {
    const stripeClient = getStripe();
    if (!stripeClient) {
      throw new Error('Stripe is not configured.');
    }

    const rateInfo = await exchangeService.getExchangeRate();
    const costUsd = creditAmount / rateInfo.rate;
    const fee = costUsd * rateInfo.buyFeeRate;
    const totalCents = Math.round((costUsd + fee) * 100);

    if (totalCents < 50) {
      throw new Error('Minimum purchase amount is $0.50');
    }

    const paymentIntent = await stripeClient.paymentIntents.create({
      amount: totalCents,
      currency: 'usd',
      metadata: {
        userId,
        creditAmount: String(creditAmount),
        exchangeRate: String(rateInfo.rate),
        type: 'credit_purchase',
      },
      description: `${creditAmount} Ogenti Credits`,
      automatic_payment_methods: { enabled: true },
    });

    logger.info(`Credit PaymentIntent created: user=${userId} credits=${creditAmount} amount=$${(totalCents / 100).toFixed(2)}`);

    return {
      clientSecret: paymentIntent.client_secret,
      paymentIntentId: paymentIntent.id,
      amount: totalCents / 100,
      credits: creditAmount,
      rate: rateInfo.rate,
      fee: Math.round(fee * 100) / 100,
    };
  }

  /** Credit user account after verified payment */
  async creditUserAfterPayment(userId: string, creditAmount: number, paymentIntentId: string) {
    const rateInfo = await exchangeService.getExchangeRate();
    const moneyAmount = creditAmount / rateInfo.rate;
    const fee = moneyAmount * rateInfo.buyFeeRate;

    await prisma.$transaction(async (tx: any) => {
      const user = await tx.user.update({
        where: { id: userId },
        data: { credits: { increment: creditAmount } },
        select: { credits: true },
      });

      await tx.creditLedger.create({
        data: {
          userId,
          amount: creditAmount,
          reason: 'EXCHANGE_BUY',
          referenceId: paymentIntentId,
          balance: user.credits,
        },
      });

      await tx.creditExchange.create({
        data: {
          userId,
          type: 'BUY',
          creditAmount,
          moneyAmount: moneyAmount + fee,
          exchangeRate: rateInfo.rate,
          fee,
          feeRate: rateInfo.buyFeeRate,
          netMoney: moneyAmount + fee,
          status: 'COMPLETED',
        },
      });
    });

    logger.info(`Credit purchase completed: user=${userId} credits=${creditAmount} pi=${paymentIntentId}`);
  }

  /** Create a Stripe Checkout session to pay for a subscription tier */
  async createSubscriptionCheckoutSession(
    userId: string,
    tier: string,
    priceUsd: number,
    tierName: string,
    dailyCredits: number,
    successUrl: string,
    cancelUrl: string,
  ) {
    const stripeClient = getStripe();
    if (!stripeClient) {
      throw new Error('Stripe is not configured. Set STRIPE_SECRET_KEY in Settings.');
    }

    const totalCents = Math.round(priceUsd * 100);
    if (totalCents < 50) {
      throw new Error('Minimum subscription amount is $0.50');
    }

    const session = await stripeClient.checkout.sessions.create({
      payment_method_types: ['card'],
      line_items: [
        {
          price_data: {
            currency: 'usd',
            product_data: {
              name: `Ogenti ${tierName} Plan — 1 Month`,
              description: `${dailyCredits} credits/day (~${dailyCredits * 30} credits/month)`,
            },
            unit_amount: totalCents,
          },
          quantity: 1,
        },
      ],
      mode: 'payment',
      success_url: successUrl,
      cancel_url: cancelUrl,
      metadata: {
        userId,
        subscriptionTier: tier.toUpperCase(),
        priceUsd: String(priceUsd),
      },
    });

    logger.info(`Stripe subscription checkout created: user=${userId} tier=${tier} amount=$${priceUsd}`);

    return {
      sessionId: session.id,
      url: session.url,
      amount: priceUsd,
      tier,
    };
  }

  /** Handle Stripe webhook events */
  async handleWebhook(payload: Buffer, signature: string) {
    const stripeClient = getStripe();
    if (!stripeClient) {
      throw new Error('Stripe not configured');
    }

    let event: any;
    try {
      event = stripeClient.webhooks.constructEvent(
        payload, signature, config.stripe.webhookSecret
      );
    } catch (err: any) {
      logger.warn(`Stripe webhook signature verification failed: ${err.message}`);
      throw new Error('Invalid webhook signature');
    }

    if (event.type === 'checkout.session.completed') {
      const session = event.data.object;
      const userId = session.metadata?.userId;

      // ── Subscription payment ────────────────────────────────────
      if (session.metadata?.subscriptionTier) {
        const tier = session.metadata.subscriptionTier;
        if (!userId || !tier) {
          logger.warn('Stripe subscription webhook: missing metadata');
          return;
        }
        try {
          await subscriptionService.activateAfterPayment(userId, tier);
          logger.info(`Stripe subscription activated: user=${userId} tier=${tier}`);
        } catch (e: any) {
          // May already be subscribed if webhook fires twice — ignore duplicate
          logger.warn(`Stripe subscription activation error (may be duplicate): ${e.message}`);
        }
        return;
      }

      // ── Credit purchase payment ─────────────────────────────────
      const creditAmount = parseInt(session.metadata?.creditAmount || '0', 10);
      const exchangeRate = parseFloat(session.metadata?.exchangeRate || '10');

      if (!userId || !creditAmount) {
        logger.warn('Stripe webhook: missing metadata');
        return;
      }

      // Credit the user
      const moneyAmount = session.amount_total / 100;
      const fee = moneyAmount * 0.05; // Buy fee is 5%

      await prisma.$transaction(async (tx: any) => {
        const user = await tx.user.update({
          where: { id: userId },
          data: { credits: { increment: creditAmount } },
          select: { credits: true },
        });

        await tx.creditLedger.create({
          data: {
            userId,
            amount: creditAmount,
            reason: 'EXCHANGE_BUY',
            referenceId: session.id,
            balance: user.credits,
          },
        });

        await tx.creditExchange.create({
          data: {
            userId,
            type: 'BUY',
            creditAmount,
            moneyAmount,
            exchangeRate,
            fee,
            feeRate: 0.05,
            netMoney: moneyAmount,
            status: 'COMPLETED',
          },
        });
      });

      logger.info(`Stripe payment completed: user=${userId} credits=${creditAmount} paid=$${moneyAmount}`);
    }

    // ── PaymentIntent succeeded (in-app Stripe Elements payment) ──
    if (event.type === 'payment_intent.succeeded') {
      const pi = event.data.object;
      const piUserId = pi.metadata?.userId;
      const piTier = pi.metadata?.subscriptionTier;

      if (piTier && piUserId) {
        try {
          await subscriptionService.activateAfterPayment(piUserId, piTier);
          logger.info(`Stripe PaymentIntent subscription activated: user=${piUserId} tier=${piTier}`);
        } catch (e: any) {
          logger.warn(`Stripe PI subscription error (may be duplicate): ${e.message}`);
        }
      }
    }
  }

  /** Create a PaymentIntent for in-app payment (Stripe Elements) */
  async createSubscriptionPaymentIntent(
    userId: string,
    tier: string,
    priceUsd: number,
    tierName: string,
    dailyCredits: number,
  ) {
    const stripeClient = getStripe();
    if (!stripeClient) {
      throw new Error('Stripe is not configured. Set STRIPE_SECRET_KEY in Settings.');
    }

    const totalCents = Math.round(priceUsd * 100);
    if (totalCents < 50) {
      throw new Error('Minimum subscription amount is $0.50');
    }

    const paymentIntent = await stripeClient.paymentIntents.create({
      amount: totalCents,
      currency: 'usd',
      metadata: {
        userId,
        subscriptionTier: tier.toUpperCase(),
        priceUsd: String(priceUsd),
        tierName,
        dailyCredits: String(dailyCredits),
        type: 'subscription',
      },
      description: `Ogenti ${tierName} Plan — ${dailyCredits} credits/day`,
      automatic_payment_methods: { enabled: true },
    });

    logger.info(`Stripe PaymentIntent created: user=${userId} tier=${tier} amount=$${priceUsd} pi=${paymentIntent.id}`);

    return {
      clientSecret: paymentIntent.client_secret,
      paymentIntentId: paymentIntent.id,
      amount: priceUsd,
      tier,
    };
  }

  /** Verify a PaymentIntent succeeded for the given user */
  async verifyPaymentIntent(paymentIntentId: string, userId: string): Promise<boolean> {
    const stripeClient = getStripe();
    if (!stripeClient) return false;

    try {
      const pi = await stripeClient.paymentIntents.retrieve(paymentIntentId);
      return pi.status === 'succeeded' && pi.metadata?.userId === userId;
    } catch (e: any) {
      logger.warn(`PaymentIntent verification failed: ${e.message}`);
      return false;
    }
  }

  /** Get Stripe configuration status for frontend */
  getStatus() {
    return {
      enabled: this.isEnabled(),
      configured: !!config.stripe.secretKey,
    };
  }

  /** Get publishable key for frontend Stripe Elements */
  getPublishableKey() {
    return config.stripe.publishableKey || '';
  }
}

export const stripeService = new StripeService();
