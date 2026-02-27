/**
 * Credits Routes — Ogenti Credit System API
 * 
 * All routes are under /api/credits/
 * 
 * Replaces Stripe-based payments with internal credit economy.
 * Now includes agent-to-agent transfers and agent purchase requests.
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, authenticateAgentOrReject, AuthRequest } from '../middleware/auth';
import { creditService } from '../services/creditService';
import { exchangeService } from '../services/exchangeService';
import prisma from '../models';

const router = Router();

// GET /api/credits/balance — Get current credit balance
router.get('/balance', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const balance = await creditService.getBalance(req.userId!);
    res.json({ success: true, data: { balance } });
  } catch (error) {
    next(error);
  }
});

// GET /api/credits/summary — Get credit summary with breakdown
router.get('/summary', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const summary = await creditService.getCreditSummary(req.userId!);
    res.json({ success: true, data: summary });
  } catch (error) {
    next(error);
  }
});

// GET /api/credits/ledger — Get credit transaction history
router.get('/ledger', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { page, limit } = req.query;
    const ledger = await creditService.getLedger(req.userId!, {
      page: page ? parseInt(page as string, 10) : 1,
      limit: limit ? parseInt(limit as string, 10) : 20,
    });
    res.json({ success: true, data: ledger });
  } catch (error) {
    next(error);
  }
});

// GET /api/credits/agent-cost/:agentId — Get real-time credit cost for an agent
router.get('/agent-cost/:agentId', async (req: any, res: Response, next: NextFunction) => {
  try {
    const agent = await prisma.agent.findUnique({
      where: { id: req.params.agentId },
      select: { id: true, price: true, tier: true, name: true },
    });
    if (!agent) {
      return res.status(404).json({ success: false, error: { message: 'Agent not found' } });
    }
    const creditCost = await creditService.getCreditCost(agent.price, agent.tier);
    const rateInfo = await exchangeService.getExchangeRate();
    res.json({
      success: true,
      data: {
        agentId: agent.id,
        name: agent.name,
        priceUsd: agent.price,
        tier: agent.tier,
        creditCost,
        exchangeRate: rateInfo.rate,
        creditPrice: rateInfo.creditPrice,
      },
    });
  } catch (error) {
    next(error);
  }
});

// POST /api/credits/purchase — Purchase an agent with credits
router.post('/purchase', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { agentId } = req.body;
    const result = await creditService.purchaseAgent(req.userId!, agentId);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent-to-Agent Credit Transfers (runtime only)
// ============================================

// POST /api/credits/transfer — Agent sends credits to another agent
router.post('/transfer', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { fromAgentId, fromAgentName, toAgentId, toAgentName, amount, reason, postId, ownerId } = req.body;
    if (!fromAgentId || !toAgentId || !amount || !reason || !ownerId) {
      return res.status(400).json({
        success: false,
        error: { message: 'fromAgentId, toAgentId, amount, reason, ownerId are required' },
      });
    }
    const result = await creditService.transferCredits(
      ownerId, fromAgentId, fromAgentName || 'Unknown',
      toAgentId, toAgentName || 'Unknown',
      Math.floor(amount), reason, postId
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Purchase Requests (runtime creates, user approves)
// ============================================

// POST /api/credits/agent-purchase-request — Agent requests to buy another agent
router.post('/agent-purchase-request', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { requestingAgentId, requestingAgentName, targetAgentSlug, reason, ownerId } = req.body;
    if (!requestingAgentId || !targetAgentSlug || !reason || !ownerId) {
      return res.status(400).json({
        success: false,
        error: { message: 'requestingAgentId, targetAgentSlug, reason, ownerId are required' },
      });
    }
    const result = await creditService.createPurchaseRequest(
      requestingAgentId, requestingAgentName || 'Unknown',
      targetAgentSlug, reason, ownerId
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/credits/agent-purchase-requests — Get all purchase requests for owner
router.get('/agent-purchase-requests', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const requests = await creditService.getPurchaseRequests(req.userId!);
    res.json({ success: true, data: requests });
  } catch (error) {
    next(error);
  }
});

// POST /api/credits/agent-purchase-requests/:id/approve — Owner approves
router.post('/agent-purchase-requests/:id/approve', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await creditService.approvePurchaseRequest(req.params.id, req.userId!);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/credits/agent-purchase-requests/:id/reject — Owner rejects
router.post('/agent-purchase-requests/:id/reject', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await creditService.rejectPurchaseRequest(req.params.id, req.userId!);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

export default router;
