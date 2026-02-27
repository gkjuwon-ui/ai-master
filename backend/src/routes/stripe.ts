/**
 * Stripe Routes — Real Payment Integration API
 * 
 * All routes are under /api/stripe/
 * 
 * Wraps Stripe Checkout for purchasing credits with real money.
 * Falls back gracefully when Stripe is not configured.
 */

import { Router, Request, Response, NextFunction } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { stripeService } from '../services/stripeService';
import { config } from '../config';

const router = Router();

// GET /api/stripe/status — Check if Stripe is configured
router.get('/status', async (_req: Request, res: Response) => {
  res.json({ success: true, data: stripeService.getStatus() });
});

// GET /api/stripe/publishable-key — Return publishable key for frontend Elements
router.get('/publishable-key', async (_req: Request, res: Response) => {
  const pk = stripeService.getPublishableKey();
  if (!pk) {
    return res.status(400).json({ success: false, error: { message: 'Stripe publishable key not configured' } });
  }
  res.json({ success: true, data: { publishableKey: pk } });
});

// POST /api/stripe/checkout — Create Stripe Checkout session
router.post('/checkout', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!stripeService.isEnabled()) {
      return res.status(400).json({
        success: false,
        error: {
          code: 'STRIPE_NOT_CONFIGURED',
          message: 'Stripe is not configured. Go to Settings and enter your Stripe API key to enable real payments.',
        },
      });
    }

    const { creditAmount } = req.body;
    if (!creditAmount || typeof creditAmount !== 'number' || creditAmount < 5) {
      return res.status(400).json({
        success: false,
        error: { message: 'creditAmount must be at least 5' },
      });
    }

    const frontendUrl = config.frontendUrl;
    const result = await stripeService.createCheckoutSession(
      req.userId!,
      Math.floor(creditAmount),
      `${frontendUrl}/credits?session=success`,
      `${frontendUrl}/credits?session=cancelled`,
    );

    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/stripe/create-payment-intent — Create PaymentIntent for in-app credit purchase
router.post('/create-payment-intent', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!stripeService.isEnabled()) {
      return res.status(400).json({
        success: false,
        error: { code: 'STRIPE_NOT_CONFIGURED', message: 'Stripe is not configured.' },
      });
    }

    const { creditAmount } = req.body;
    if (!creditAmount || typeof creditAmount !== 'number' || creditAmount < 5) {
      return res.status(400).json({
        success: false,
        error: { message: 'creditAmount must be at least 5' },
      });
    }

    const result = await stripeService.createCreditPaymentIntent(req.userId!, Math.floor(creditAmount));
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/stripe/confirm-credit — Confirm credit purchase after in-app payment
router.post('/confirm-credit', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { paymentIntentId, creditAmount } = req.body;
    if (!paymentIntentId || !creditAmount) {
      return res.status(400).json({
        success: false,
        error: { message: 'paymentIntentId and creditAmount are required' },
      });
    }

    const verified = await stripeService.verifyPaymentIntent(paymentIntentId, req.userId!);
    if (!verified) {
      return res.status(400).json({
        success: false,
        error: { message: 'Payment could not be verified' },
      });
    }

    await stripeService.creditUserAfterPayment(req.userId!, Math.floor(creditAmount), paymentIntentId);
    res.json({ success: true, data: { credited: creditAmount } });
  } catch (error) {
    next(error);
  }
});

// POST /api/stripe/webhook — Stripe webhook handler
router.post('/webhook', async (req: Request, res: Response) => {
  try {
    const signature = req.headers['stripe-signature'] as string;
    if (!signature) {
      return res.status(400).json({ error: 'Missing stripe-signature header' });
    }

    // req.body should be raw buffer for webhook verification
    // Express raw body must be configured for this route
    await stripeService.handleWebhook(req.body, signature);
    res.json({ received: true });
  } catch (error: any) {
    res.status(400).json({ error: error.message });
  }
});

export default router;
