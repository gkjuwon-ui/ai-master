import { Router, Request, Response, NextFunction } from 'express';
import { authenticate, optionalAuth, requireDeveloper, AuthRequest } from '../middleware/auth';
import { validate } from '../middleware/validation';
import { agentCreateSchema, agentUpdateSchema, agentQuerySchema, reviewSchema } from '../utils/validators';
import { agentService } from '../services/agentService';
import { agentReviewService } from '../services/agentReviewService';
import { dashboardAnalyticsService } from '../services/dashboardAnalyticsService';
import { config } from '../config';
import prisma from '../models';

const router = Router();

// GET /api/agents - List agents (public)
router.get('/', optionalAuth, validate(agentQuerySchema, 'query'), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await agentService.list(req.query as any);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/purchased - Get user's purchased agents
router.get('/purchased', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const purchases = await agentService.getPurchasedAgents(req.userId!);
    res.json({ success: true, data: purchases });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/dashboard-analytics
router.get('/dashboard-analytics', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const data = await dashboardAnalyticsService.getAnalytics(req.userId!);
    res.json({ success: true, data });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/community-learnings/:agentId - Proxy to runtime
router.get('/community-learnings/:agentId', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  const emptyData = { learnings: [], stats: { total_count: 0, categories: {}, recent_7d: 0 } };
  try {
    const { agentId } = req.params;
    const runtimeUrl = config.agentRuntime.url;
    const url = new URL(`/community-learnings/${agentId}`, runtimeUrl);
    const httpModule = url.protocol === 'https:' ? await import('https') : await import('http');

    const body: string = await new Promise((resolve, reject) => {
      const r = httpModule.get(url.toString(), { timeout: 5000 }, (resp) => {
        const chunks: Buffer[] = [];
        resp.on('data', (c: Buffer) => chunks.push(c));
        resp.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')));
      });
      r.on('error', reject);
      r.on('timeout', () => { r.destroy(); reject(new Error('timeout')); });
    });

    const data = JSON.parse(body);
    res.json({ success: true, data });
  } catch (error) {
    res.json({ success: true, data: emptyData });
  }
});

// GET /api/agents/my - Get developer's own agents
router.get('/my', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agents = await agentService.getDeveloperAgents(req.userId!);
    res.json({ success: true, data: agents });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/:id - Get agent by ID
router.get('/:id', optionalAuth, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await agentService.getById(req.params.id);
    res.json({ success: true, data: agent });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/slug/:slug - Get agent by slug
router.get('/slug/:slug', optionalAuth, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await agentService.getBySlug(req.params.slug);
    res.json({ success: true, data: agent });
  } catch (error) {
    next(error);
  }
});

// POST /api/agents - Create agent (developer only)
router.post('/', authenticate, requireDeveloper, validate(agentCreateSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await agentService.create(req.userId!, req.body);
    res.status(201).json({ success: true, data: agent });
  } catch (error) {
    next(error);
  }
});

// PUT /api/agents/:id - Update agent
router.put('/:id', authenticate, requireDeveloper, validate(agentUpdateSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await agentService.update(req.params.id, req.userId!, req.body);
    res.json({ success: true, data: agent });
  } catch (error) {
    next(error);
  }
});

// POST /api/agents/:id/publish
router.post('/:id/publish', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await agentService.publish(req.params.id, req.userId!);
    res.json({ success: true, data: agent });
  } catch (error) {
    next(error);
  }
});

// POST /api/agents/:id/unpublish
router.post('/:id/unpublish', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await agentService.unpublish(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// DELETE /api/agents/:id
router.delete('/:id', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await agentService.delete(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/agents/:id/reviews
router.post('/:id/reviews', authenticate, validate(reviewSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const review = await agentService.addReview(req.params.id, req.userId!, req.body);
    res.status(201).json({ success: true, data: review });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/:id/reviews
router.get('/:id/reviews', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const limit = parseInt(req.query.limit as string) || 20;
    const result = await agentService.getReviews(req.params.id, page, limit);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/:id/access - Check if user has access to agent
router.get('/:id/access', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const hasAccess = await agentService.hasAccess(req.userId!, req.params.id);
    res.json({ success: true, data: { hasAccess } });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/:id/review-report - Get security review report
router.get('/:id/review-report', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const report = await agentReviewService.getReviewReport(req.params.id);
    res.json({ success: true, data: report });
  } catch (error) {
    next(error);
  }
});

// POST /api/agents/:id/re-review - Re-submit rejected agent for review
router.post('/:id/re-review', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const report = await agentReviewService.reReview(req.params.id, req.userId!);
    const status = report.verdict === 'APPROVED' ? 'published' : 'rejected';
    res.json({
      success: true,
      data: {
        verdict: report.verdict,
        overallRisk: report.overallRisk,
        summary: report.summary,
        findingCount: report.findings.length,
        status,
      },
    });
  } catch (error) {
    next(error);
  }
});

// ═══════════════════════════════════════════════════════════
// Per-Agent LLM Assignment
// ═══════════════════════════════════════════════════════════

// PUT /api/agents/:id/llm-config - Assign LLM config to an agent
router.put('/:id/llm-config', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { llmConfigId } = req.body;
    const agent = await prisma.agent.findUnique({ where: { id: req.params.id } });
    if (!agent) return res.status(404).json({ success: false, error: 'Agent not found' });

    // Verify user owns or has purchased this agent
    const purchase = await prisma.purchase.findFirst({
      where: { userId: req.userId!, agentId: agent.id, status: 'COMPLETED' },
    });
    if (!purchase && agent.developerId !== req.userId!) {
      return res.status(403).json({ success: false, error: 'Not your agent' });
    }

    // Verify user owns this LLM config (if setting, not clearing)
    if (llmConfigId) {
      const llmConfig = await prisma.lLMConfig.findUnique({ where: { id: llmConfigId } });
      if (!llmConfig || llmConfig.userId !== req.userId!) {
        return res.status(403).json({ success: false, error: 'LLM config not found or not yours' });
      }
    }

    const updated = await prisma.agent.update({
      where: { id: req.params.id },
      data: { llmConfigId: llmConfigId || null },
      include: { llmConfig: { select: { id: true, name: true, provider: true, model: true } } },
    });
    res.json({ success: true, data: updated });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/:id/llm-config - Get agent's assigned LLM config
router.get('/:id/llm-config', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agent = await prisma.agent.findUnique({
      where: { id: req.params.id },
      include: { llmConfig: { select: { id: true, name: true, provider: true, model: true } } },
    });
    if (!agent) return res.status(404).json({ success: false, error: 'Agent not found' });
    res.json({ success: true, data: { llmConfigId: agent.llmConfigId, llmConfig: (agent as any).llmConfig } });
  } catch (error) {
    next(error);
  }
});

// GET /api/agents/all/llm-assignments - Get all agent LLM assignments for the current user
router.get('/all/llm-assignments', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Get all agents that have LLM configs owned by this user
    const agents = await prisma.agent.findMany({
      where: {
        llmConfigId: { not: null },
        llmConfig: { userId: req.userId! },
      },
      select: {
        id: true,
        name: true,
        slug: true,
        tier: true,
        domain: true,
        icon: true,
        llmConfigId: true,
        llmConfig: { select: { id: true, name: true, provider: true, model: true } },
      },
    });
    res.json({ success: true, data: agents });
  } catch (error) {
    next(error);
  }
});

// ═══════════════════════════════════════════════════════════
// Per-Agent Persona (Prompt Engineering)
// ═══════════════════════════════════════════════════════════

// GET /api/agents/:id/persona - Get user's custom persona for an agent
router.get('/:id/persona', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const purchase = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId: req.userId!, agentId: req.params.id } },
      select: { persona: true },
    });
    if (!purchase) return res.status(404).json({ success: false, error: 'Agent not purchased' });
    res.json({ success: true, data: { persona: purchase.persona || '' } });
  } catch (error) {
    next(error);
  }
});

// PUT /api/agents/:id/persona - Save user's custom persona for an agent
router.put('/:id/persona', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { persona } = req.body;
    if (typeof persona !== 'string') {
      return res.status(400).json({ success: false, error: 'persona must be a string' });
    }
    if (persona.length > 2000) {
      return res.status(400).json({ success: false, error: 'persona must be 2000 characters or less' });
    }

    const purchase = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId: req.userId!, agentId: req.params.id } },
    });
    if (!purchase) return res.status(404).json({ success: false, error: 'Agent not purchased' });

    const updated = await prisma.purchase.update({
      where: { id: purchase.id },
      data: { persona: persona.trim() || null },
      select: { persona: true },
    });
    res.json({ success: true, data: { persona: updated.persona || '' } });
  } catch (error) {
    next(error);
  }
});

export default router;
