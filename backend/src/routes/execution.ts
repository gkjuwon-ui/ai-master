import { Router, Response, NextFunction } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { validate } from '../middleware/validation';
import { executionCreateSchema } from '../utils/validators';
import { executionService } from '../services/executionService';
import { ogentTokenService } from '../services/ogentTokenService';
import { config } from '../config';
import crypto from 'crypto';

const router = Router();

/** Timing-safe comparison for runtime secret to prevent timing attacks */
function verifyRuntimeSecret(provided: string | string[] | undefined): boolean {
  if (!provided || Array.isArray(provided)) return false;
  const expected = config.agentRuntime.secret;
  if (!expected || expected === 'agent-runtime-secret') return false;
  if (provided.length !== expected.length) return false;
  return crypto.timingSafeEqual(Buffer.from(provided), Buffer.from(expected));
}

// POST /api/execution/check-capabilities - Check if selected agents match required capabilities
router.post('/check-capabilities', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { prompt, agentIds } = req.body;
    if (!prompt || !agentIds || !Array.isArray(agentIds)) {
      res.status(400).json({ success: false, error: { message: 'prompt and agentIds are required' } });
      return;
    }
    const result = await executionService.checkCapabilities(req.userId!, { prompt, agentIds });
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution - Create execution session
router.post('/', authenticate, validate(executionCreateSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const session = await executionService.createSession(req.userId!, req.body);
    res.status(201).json({ success: true, data: session });
  } catch (error) {
    next(error);
  }
});

// GET /api/execution - List user sessions
router.get('/', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const limit = parseInt(req.query.limit as string) || 20;
    const result = await executionService.getUserSessions(req.userId!, page, limit);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/execution/:id - Get session details
router.get('/:id', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const session = await executionService.getSession(req.params.id, req.userId!);
    res.json({ success: true, data: session });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/:id/start - Start execution
router.post('/:id/start', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await executionService.startExecution(req.params.id, req.userId!);
    res.json({ success: true, data: { message: 'Execution started' } });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/:id/pause
router.post('/:id/pause', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await executionService.pauseExecution(req.params.id, req.userId!);
    res.json({ success: true, data: { message: 'Execution paused' } });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/:id/cancel
router.post('/:id/cancel', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await executionService.cancelExecution(req.params.id, req.userId!);
    res.json({ success: true, data: { message: 'Execution cancelled' } });
  } catch (error) {
    next(error);
  }
});

// GET /api/execution/:id/logs
router.get('/:id/logs', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const logs = await executionService.getSessionLogs(req.params.id, req.userId!, req.query.after as string);
    res.json({ success: true, data: logs });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/callback - Runtime callback (internal, generic route)
router.post('/callback', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req.headers['x-runtime-secret'])) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime secret' } });
      return;
    }
    const sessionId = req.body.sessionId;
    if (!sessionId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Missing sessionId' } });
      return;
    }
    await executionService.handleRuntimeCallback(sessionId, req.body);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/:id/callback - Runtime callback (internal)
router.post('/:id/callback', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req.headers['x-runtime-secret'])) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime secret' } });
      return;
    }
    await executionService.handleRuntimeCallback(req.params.id, req.body);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/execution/ogent-token-report - Runtime reports ogent-1.0 token usage for credit deduction
router.post('/ogent-token-report', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!verifyRuntimeSecret(req.headers['x-runtime-secret'])) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime secret' } });
      return;
    }
    const { ownerId, mode, inputTokens, outputTokens, sessionId } = req.body;
    if (!ownerId || !mode || inputTokens == null || outputTokens == null) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Missing required fields' } });
      return;
    }
    const result = await ogentTokenService.deductTokenCredits(
      ownerId, mode, inputTokens, outputTokens, sessionId
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/execution/ogent-pricing - Get ogent-1.0 pricing info for UI
router.get('/ogent-pricing', (_req, res) => {
  res.json({ success: true, data: ogentTokenService.getPricingInfo() });
});

// DELETE /api/execution/:id
router.delete('/:id', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await executionService.deleteSession(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

export default router;
