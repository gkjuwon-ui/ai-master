/**
 * Subscription Routes — Daily Credit Drip API
 * 
 * All routes are under /api/subscriptions/
 * 
 * Subscriptions are priced in real money (USD).
 * Subscribers receive daily credit drips based on their tier.
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { subscriptionService, SUBSCRIPTION_TIERS, SubscriptionTierKey } from '../services/subscriptionService';
import { stripeService } from '../services/stripeService';
import { exchangeService } from '../services/exchangeService';

const router = Router();

// GET /api/subscriptions/tiers — Get available subscription tiers
router.get('/tiers', async (_req: any, res: Response, next: NextFunction) => {
  try {
    const tiers = await subscriptionService.getTiers();
    res.json({ success: true, data: tiers });
  } catch (error) {
    next(error);
  }
});

// GET /api/subscriptions/current — Get user's current subscription + drip status
router.get('/current', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const subscription = await subscriptionService.getSubscription(req.userId!);
    res.json({ success: true, data: subscription });
  } catch (error) {
    next(error);
  }
});

// POST /api/subscriptions/subscribe — Subscribe to a tier
router.post('/subscribe', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { tier } = req.body;
    if (!tier) {
      return res.status(400).json({
        success: false,
        error: { code: 'MISSING_TIER', message: 'tier is required' },
      });
    }

    const tierKey = tier.toUpperCase() as SubscriptionTierKey;
    const tierInfo = SUBSCRIPTION_TIERS[tierKey];
    if (!tierInfo) {
      return res.status(400).json({
        success: false,
        error: { code: 'INVALID_TIER', message: `Invalid tier. Valid options: ${Object.keys(SUBSCRIPTION_TIERS).join(', ')}` },
      });
    }

    // If Stripe is configured — return PaymentIntent clientSecret for in-app payment
    if (stripeService.isEnabled()) {
      // Calculate dynamic USD price
      let priceUsd: number;
      try {
        const rateInfo = await exchangeService.getExchangeRate();
        const rate = rateInfo.rate;
        priceUsd = Math.round((tierInfo.monthlyCredits / rate) * 1.25 * 100) / 100;
      } catch {
        priceUsd = Math.round((tierInfo.monthlyCredits / 10) * 1.25 * 100) / 100;
      }

      const result = await stripeService.createSubscriptionPaymentIntent(
        req.userId!,
        tierKey,
        priceUsd,
        tierInfo.name,
        tierInfo.dailyCredits,
      );

      return res.json({ success: true, data: { ...result, requiresPayment: true } });
    }

    // Stripe not configured — subscribe directly (dev/admin mode)
    const subscription = await subscriptionService.subscribe(req.userId!, tier);
    res.json({ success: true, data: subscription });
  } catch (error) {
    next(error);
  }
});

// POST /api/subscriptions/cancel — Cancel current subscription
router.post('/cancel', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await subscriptionService.cancel(req.userId!);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/subscriptions/confirm — Confirm subscription after in-app payment
router.post('/confirm', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { tier, paymentIntentId } = req.body;
    if (!tier || !paymentIntentId) {
      return res.status(400).json({
        success: false,
        error: { code: 'MISSING_PARAMS', message: 'tier and paymentIntentId are required' },
      });
    }

    // Verify the PaymentIntent actually succeeded with Stripe
    if (stripeService.isEnabled()) {
      const verified = await stripeService.verifyPaymentIntent(paymentIntentId, req.userId!);
      if (!verified) {
        return res.status(400).json({
          success: false,
          error: { code: 'PAYMENT_NOT_VERIFIED', message: 'Payment could not be verified' },
        });
      }
    }

    const subscription = await subscriptionService.activateAfterPayment(req.userId!, tier);
    res.json({ success: true, data: subscription });
  } catch (error) {
    next(error);
  }
});

// PUT /api/subscriptions/change-tier — Change subscription tier
router.put('/change-tier', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { tier } = req.body;
    if (!tier) {
      return res.status(400).json({
        success: false,
        error: { code: 'MISSING_TIER', message: 'tier is required' },
      });
    }

    return res.status(400).json({
      success: false,
      error: {
        code: 'TIER_CHANGE_REQUIRES_PAYMENT',
        message: 'Tier change requires a new checkout. Please use the Subscribe flow for the target tier.',
      },
    });
  } catch (error) {
    next(error);
  }
});

// POST /api/subscriptions/claim-daily — Claim daily credit drip
router.post('/claim-daily', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await subscriptionService.claimDaily(req.userId!);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

export default router;
