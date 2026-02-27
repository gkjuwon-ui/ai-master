/**
 * Exchange Routes — Credit ↔ Money Exchange API
 * 
 * All routes are under /api/exchange/
 * 
 * Platform earns revenue by taking a fee on each exchange.
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { exchangeService } from '../services/exchangeService';

const router = Router();

// GET /api/exchange/rate — Get current exchange rate
router.get('/rate', async (_req: any, res: Response, next: NextFunction) => {
  try {
    const rate = await exchangeService.getExchangeRate();
    res.json({ success: true, data: rate });
  } catch (error) {
    next(error);
  }
});

// POST /api/exchange/buy — Buy credits (requires Stripe payment)
router.post('/buy', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  // Direct credit grants without payment are disabled.
  // All purchases must go through Stripe Checkout (/api/stripe/checkout).
  return res.status(400).json({
    success: false,
    error: {
      code: 'PAYMENT_REQUIRED',
      message: 'Credit purchases require card payment. Please use the "Pay with Card" option.',
    },
  });
});

// POST /api/exchange/sell — Sell credits for money
router.post('/sell', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { creditAmount } = req.body;
    if (!creditAmount || typeof creditAmount !== 'number' || creditAmount <= 0) {
      return res.status(400).json({
        success: false,
        error: { code: 'INVALID_AMOUNT', message: 'creditAmount must be a positive number' },
      });
    }

    const result = await exchangeService.sellCredits(req.userId!, Math.floor(creditAmount));
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/exchange/history — Get exchange history
router.get('/history', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page, limit } = req.query;
    const history = await exchangeService.getHistory(req.userId!, {
      page: page ? parseInt(page as string, 10) : 1,
      limit: limit ? parseInt(limit as string, 10) : 20,
    });
    res.json({ success: true, data: history });
  } catch (error) {
    next(error);
  }
});

// GET /api/exchange/stats — Platform exchange stats (admin only)
router.get('/stats', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if ((req as any).userRole !== 'ADMIN') {
      return res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Admin access required' } });
    }
    const stats = await exchangeService.getExchangeStats();
    res.json({ success: true, data: stats });
  } catch (error) {
    next(error);
  }
});

export default router;
