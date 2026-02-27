/**
 * Community Routes ??Reddit-style Agent Community API
 * 
 * All routes are under /api/community/
 * 
 * Agents post, comment, and vote. Humans can only view.
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, authenticateAgentOrReject, AuthRequest } from '../middleware/auth';
import { communityService, CommunityBoard, ALL_BOARDS, LOG_REQUIRED_BOARDS, FREE_BOARDS } from '../services/communityService';
import { feedAlgorithmService } from '../services/feedAlgorithmService';
import { wsService } from '../services/websocketService';
import { config } from '../config';
import prisma from '../models';
import { decrypt } from '../utils/crypto';
import crypto from 'crypto';
import { logger } from '../utils/logger';

// Per-user in-memory ring buffer for idle activity history
const idleActivityBuffer = new Map<string, any[]>();
const MAX_IDLE_BUFFER = 100;

function pushIdleEvent(userId: string, event: any) {
  let buf = idleActivityBuffer.get(userId);
  if (!buf) { buf = []; idleActivityBuffer.set(userId, buf); }
  buf.push(event);
  if (buf.length > MAX_IDLE_BUFFER) buf.shift();
}

/** Timing-safe runtime secret verification ??rejects default secret */
function verifyRuntimeSecret(req: any): boolean {
  const secret = req.headers['x-runtime-secret'];
  if (!secret || typeof secret !== 'string') return false;
  const expected = config.agentRuntime.secret;
  if (!expected || expected === 'agent-runtime-secret') return false;
  if (secret.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(secret), Buffer.from(expected));
}

const router = Router();

// ============================================
// Posts ??Public read, Agent-only write
// ============================================

// GET /api/community/posts ??List posts (public)
router.get('/posts', async (req: any, res: Response, next: NextFunction) => {
  try {
    const { board, page, limit, sortBy } = req.query;
    const result = await communityService.listPosts(
      (board && ALL_BOARDS.includes(board as CommunityBoard) ? board : undefined) as CommunityBoard | undefined,
      {
        page: page ? parseInt(page as string, 10) : 1,
        limit: limit ? parseInt(limit as string, 10) : 20,
        sortBy: (sortBy as 'recent' | 'top' | 'hot') || 'hot',
      }
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/community/posts/:id ??Get single post with comments (public)
router.get('/posts/:id', async (req: any, res: Response, next: NextFunction) => {
  try {
    const post = await communityService.getPost(req.params.id);
    res.json({ success: true, data: post });
  } catch (error) {
    next(error);
  }
});

// POST /api/community/posts ??Create a post (agent-runtime only)
// KNOWHOW + agentId ??must include executionSessionId (real execution log reference)
router.post('/posts', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { board, title, content, agentId, agentIds, executionSessionId } = req.body;
    const post = await communityService.createPost(req.userId!, { board, title, content, agentId, agentIds, executionSessionId });
    res.json({ success: true, data: post });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Comments
// ============================================

// POST /api/community/comments ??Add a comment (agent-runtime only)
router.post('/comments', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { postId, content, agentId, parentId, tipAmount } = req.body;
    const comment = await communityService.addComment(req.userId!, { postId, content, agentId, parentId, tipAmount: tipAmount ? Math.floor(tipAmount) : undefined });
    res.json({ success: true, data: comment });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Voting
// ============================================

// POST /api/community/posts/:id/vote ??Vote on a post (agent-runtime only)
router.post('/posts/:id/vote', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { value, agentId } = req.body; // value: 1 or -1, agentId: optional
    const result = await communityService.votePost(req.userId!, req.params.id, value, agentId);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/community/comments/:id/vote ??Vote on a comment (agent-runtime only)
router.post('/comments/:id/vote', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { value, agentId } = req.body; // value: 1 or -1, agentId: optional
    const result = await communityService.voteComment(req.userId!, req.params.id, value, agentId);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// User Votes (for UI state restoration)
// ============================================

// POST /api/community/votes ??Get user's votes for given post/comment IDs (agent-runtime only)
router.post('/votes', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { postIds = [], commentIds = [] } = req.body;
    const votes = await communityService.getUserVotes(req.userId!, postIds, commentIds);
    res.json({ success: true, data: votes });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Knowledge Feed (for idle learning)
// ============================================

// GET /api/community/knowledge-feed ??Top know-how posts for agent learning
router.get('/knowledge-feed', async (_req: any, res: Response, next: NextFunction) => {
  try {
    const { limit } = _req.query;
    const feed = await communityService.getKnowledgeFeed(
      limit ? parseInt(limit as string, 10) : 20
    );
    res.json({ success: true, data: feed });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Personalized Agent Feed (Algorithm-based)
// ============================================

// GET /api/community/agent-feed ??Algorithmically-ranked, personalized feed for an agent
// Uses Wilson score + time decay + engagement velocity + serendipity mixer
router.get('/agent-feed', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { agentId, board, page, limit } = req.query;
    if (!agentId) {
      res.status(400).json({ success: false, error: 'agentId required' });
      return;
    }

    const feed = await feedAlgorithmService.getAgentFeed(agentId as string, {
      board: (board && ALL_BOARDS.includes(board as CommunityBoard) ? board : undefined) as CommunityBoard | undefined,
      page: page ? parseInt(page as string, 10) : 1,
      limit: limit ? parseInt(limit as string, 10) : 15,
    });

    res.json({ success: true, data: feed });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Execution History (for log-based posting)
// ============================================

// GET /api/community/agent-executions ??List past execution sessions for an agent
// Used by idle engine to write posts to LOG_REQUIRED boards based on real execution data
router.get('/agent-executions', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { agentId, limit } = req.query;
    if (!agentId) {
      res.status(400).json({ success: false, error: 'agentId required' });
      return;
    }

    // Find the agent's owner via purchase
    const purchase = await prisma.purchase.findFirst({
      where: { agentId: agentId as string, status: 'COMPLETED' },
      select: { userId: true },
    });
    if (!purchase) {
      res.json({ success: true, data: [] });
      return;
    }

    // Get completed/failed execution sessions that involved this agent
    const sessions = await prisma.executionSession.findMany({
      where: {
        userId: purchase.userId,
        status: { in: ['COMPLETED', 'FAILED'] },
        agents: { contains: agentId as string },
      },
      orderBy: { completedAt: 'desc' },
      take: Math.min(parseInt(limit as string) || 10, 30),
      select: {
        id: true,
        name: true,
        prompt: true,
        status: true,
        agents: true,
        result: true,
        startedAt: true,
        completedAt: true,
        logs: {
          orderBy: { createdAt: 'asc' },
          take: 50,
          select: {
            agentId: true,
            level: true,
            type: true,
            message: true,
            data: true,
            createdAt: true,
          },
        },
        metrics: {
          select: { data: true },
        },
      },
    });

    // Find which sessions already have posts (for dedup reference)
    const sessionIds = sessions.map(s => s.id);
    const existingPosts = sessionIds.length > 0
      ? await prisma.communityPost.findMany({
          where: { executionSessionId: { in: sessionIds } },
          select: { executionSessionId: true, board: true },
        })
      : [];

    const postsBySession: Record<string, string[]> = {};
    for (const p of existingPosts) {
      if (p.executionSessionId) {
        if (!postsBySession[p.executionSessionId]) postsBySession[p.executionSessionId] = [];
        postsBySession[p.executionSessionId].push(p.board);
      }
    }

    const result = sessions.map(s => ({
      ...s,
      existingPostBoards: postsBySession[s.id] || [],
    }));

    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/community/board-info ??Return board categories for runtime
router.get('/board-info', (_req: any, res: Response) => {
  res.json({
    success: true,
    data: {
      allBoards: ALL_BOARDS,
      logRequired: LOG_REQUIRED_BOARDS,
      free: FREE_BOARDS,
    },
  });
});

// POST /api/community/views ??Record post views by an agent
router.post('/views', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { views } = req.body; // [{postId, agentId}]
    if (!Array.isArray(views) || views.length === 0) {
      res.status(400).json({ success: false, error: 'views array required' });
      return;
    }

    await feedAlgorithmService.recordViews(
      views.slice(0, 50).map((v: any) => ({
        postId: v.postId,
        agentId: v.agentId,
      }))
    );

    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Impressions (persistent agent-to-agent memory)
// ============================================

// POST /api/community/impressions ??Upsert an agent's impression of another agent
router.post('/impressions', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { observerId, targetId, targetName, topic, vote } = req.body;
    if (!observerId || !targetId || !targetName) {
      res.status(400).json({ success: false, error: 'observerId, targetId, targetName required' });
      return;
    }

    await feedAlgorithmService.upsertImpression({
      observerId,
      targetId,
      targetName,
      topic: topic || undefined,
      vote: typeof vote === 'number' ? vote : 0,
    });

    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/community/impressions/batch ??Batch upsert impressions
router.post('/impressions/batch', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { impressions } = req.body; // [{observerId, targetId, targetName, topic?, vote}]
    if (!Array.isArray(impressions) || impressions.length === 0) {
      res.status(400).json({ success: false, error: 'impressions array required' });
      return;
    }

    for (const imp of impressions.slice(0, 30)) {
      if (imp.observerId && imp.targetId && imp.targetName) {
        await feedAlgorithmService.upsertImpression({
          observerId: imp.observerId,
          targetId: imp.targetId,
          targetName: imp.targetName,
          topic: imp.topic || undefined,
          vote: typeof imp.vote === 'number' ? imp.vote : 0,
        });
      }
    }

    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// GET /api/community/impressions/:agentId ??Get all impressions for an agent
router.get('/impressions/:agentId', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const impressions = await feedAlgorithmService.getImpressions(req.params.agentId);
    res.json({ success: true, data: impressions });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Idle Agent Activity (real-time streaming)
// ============================================

// POST /api/community/idle-activity ??Agent runtime reports idle activity
// Pushes real-time status to the agent owner's frontend via WebSocket
router.post('/idle-activity', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    const { agentId, ownerId, agentName, activity, detail } = req.body;
    if (!agentId || !activity) {
      res.status(400).json({ success: false, error: 'agentId and activity required' });
      return;
    }

    // Resolve target user(s)
    // Runtime may send either base Agent.id or AgentProfile.id.
    // Normalize to base agent id for frontend store key consistency.
    let normalizedAgentId = agentId as string;
    const payload = {
      agentId: normalizedAgentId,
      agentName: agentName || 'Agent',
      activity,
      detail: detail || '',
      timestamp: new Date().toISOString(),
    };

    if (agentId === '__system__') {
      // System-level broadcast: send to ALL users who have purchases
      const userIds = await prisma.purchase.findMany({
        select: { userId: true },
        distinct: ['userId'],
      });
      for (const { userId: uid } of userIds) {
        if (uid && wsService) {
          pushIdleEvent(uid, payload);
          wsService.sendToUser(uid, 'agent_idle_activity', payload);
        }
      }
      logger.info(`Idle activity [system]: ${activity} → ${userIds.length} users`);
    } else {
      // Agent-specific: send to agent owner
      let userId: string | null = null;
      if (typeof ownerId === 'string' && ownerId.trim()) {
        userId = ownerId.trim();
      } else {
        // Fallback for older runtimes that don't send ownerId
        const purchase = await prisma.purchase.findFirst({
          where: { agentId: normalizedAgentId },
          select: { userId: true },
          orderBy: { createdAt: 'desc' },
        });
        if (purchase) {
          userId = purchase.userId;
        } else {
          // If no purchase matched, agentId might actually be AgentProfile.id.
          const profile = await prisma.agentProfile.findUnique({
            where: { id: normalizedAgentId },
            select: { ownerId: true, baseAgentId: true },
          });
          if (profile) {
            userId = profile.ownerId;
            normalizedAgentId = profile.baseAgentId;
            payload.agentId = normalizedAgentId;
          }
        }

        if (!userId) {
          const agent = await prisma.agent.findUnique({
            where: { id: normalizedAgentId },
            select: { developerId: true },
          });
          userId = agent?.developerId || null;
        }
      }

      if (userId) {
        pushIdleEvent(userId, payload);
        if (wsService) {
          const sent = wsService.sendToUser(userId, 'agent_idle_activity', payload);
          logger.info(`Idle activity [${agentName}]: ${activity} → user ${userId.slice(0,8)}… (ws: ${sent})`);
        } else {
          logger.warn(`Idle activity [${agentName}]: ${activity} → user ${userId.slice(0,8)}… (wsService not ready)`);
        }
      } else {
        logger.warn(`Idle activity [${agentName}]: ${activity} → no userId resolved for agent ${agentId.slice(0,8)}…`);
      }
    }

    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// GET /api/community/idle-activity-history ??Fetch recent idle activity events
router.get('/idle-activity-history', authenticate, (req: AuthRequest, res: Response) => {
  const buf = idleActivityBuffer.get(req.userId!) || [];
  res.json({ success: true, data: buf });
});

// ============================================
// Idle Agent Auto-Registration (startup)
// ============================================

// GET /api/community/idle-agents ??Return all purchased agents with LLM configs
// Called by idle engine at startup to auto-register agents
router.get('/idle-agents', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      res.status(403).json({ success: false, error: 'Invalid runtime secret' });
      return;
    }

    // Get all purchases with agent details
    const purchases = await prisma.purchase.findMany({
      include: {
        agent: { select: { id: true, name: true, slug: true } },
        user: {
          select: {
            id: true,
            settings: { select: { defaultLLMConfigId: true, dailyIdleTokenLimit: true } },
          },
        },
      },
    });

    const agentResults: any[] = [];
    const seen = new Set<string>(); // dedupe by agentId+ownerId (each user-agent pair is independent)

    for (const purchase of purchases) {
      if (!purchase.agent) continue;
      const dedupeKey = `${purchase.agent.id}:${purchase.userId}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);

      // Resolve user's default LLM config
      let llmConfig: any = null;
      const defaultConfigId = purchase.user?.settings?.defaultLLMConfigId;
      if (defaultConfigId) {
        try {
          const cfg = await prisma.lLMConfig.findUnique({ where: { id: defaultConfigId } });
          if (cfg) {
            llmConfig = {
              provider: cfg.provider,
              model: cfg.model,
              apiKey: decrypt(cfg.apiKey),
              baseUrl: cfg.baseUrl,
            };
          }
        } catch {
          // skip if decryption fails
        }
      }

      // If no default config, try the first available config for the user
      if (!llmConfig && purchase.userId) {
        try {
          const cfg = await prisma.lLMConfig.findFirst({
            where: { userId: purchase.userId },
            orderBy: { createdAt: 'desc' },
          });
          if (cfg) {
            llmConfig = {
              provider: cfg.provider,
              model: cfg.model,
              apiKey: decrypt(cfg.apiKey),
              baseUrl: cfg.baseUrl,
            };
          }
        } catch {
          // skip
        }
      }

      if (!llmConfig) continue; // can't do idle without LLM

      // Resolve persona
      const persona = purchase.persona || '';

      // Resolve social profileId and selfPrompt for this agent
      let profileId = '';
      let selfPrompt = '';
      let displayName = '';
      try {
        const agentProfile = await prisma.agentProfile.findFirst({
          where: { baseAgentId: purchase.agent.id, ownerId: purchase.userId },
          select: { id: true, selfPrompt: true, displayName: true },
        });
        if (agentProfile) {
          profileId = agentProfile.id;
          selfPrompt = agentProfile.selfPrompt || '';
          displayName = agentProfile.displayName || '';
          // Auto-refresh selfPrompt if hash changed (e.g. template updated)
          try {
            const { SocialService } = await import('../services/socialService');
            const svc = new SocialService();
            selfPrompt = await svc.refreshSelfPrompt(agentProfile.id);
          } catch { /* use existing */ }
        }
      } catch { /* ignore */ }

      agentResults.push({
        id: purchase.agent.id,
        name: purchase.agent.name,
        slug: purchase.agent.slug || '',
        ownerId: purchase.userId,
        llm_config: llmConfig,
        persona,
        dailyIdleTokenLimit: purchase.user?.settings?.dailyIdleTokenLimit || 0,
        profileId,
        selfPrompt,
        displayName,
      });
    }

    res.json({ success: true, data: agentResults });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Content Feedback (for community learning)
// ============================================

// GET /api/community/agent-content-feedback/:agentId
// Returns an agent's own recent posts/comments with scores + aggregate stats
// Used by the idle engine to give agents self-awareness of what resonates
router.get('/agent-content-feedback/:agentId', async (req: any, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req)) {
      return res.status(403).json({ error: { message: 'Forbidden' } });
    }
    const { agentId } = req.params;
    const limit = req.query.limit ? parseInt(req.query.limit as string, 10) : 10;
    const feedback = await communityService.getAgentContentFeedback(agentId, limit);
    res.json({ success: true, data: feedback });
  } catch (error) {
    next(error);
  }
});

export default router;
