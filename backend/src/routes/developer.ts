import { Router, Response, NextFunction, Request } from 'express';
import multer from 'multer';
import path from 'path';
import { authenticate, requireDeveloper, AuthRequest } from '../middleware/auth';
import { pluginService } from '../services/pluginService';
import { agentService } from '../services/agentService';
import { config } from '../config';

const router = Router();

const upload = multer({
  dest: path.join(config.upload.dir, 'bundles'),
  limits: { fileSize: 50 * 1024 * 1024 }, // 50MB
  fileFilter: (_req, file, cb) => {
    const allowed = ['.zip', '.tar.gz', '.tgz'];
    const ext = path.extname(file.originalname).toLowerCase();
    if (allowed.includes(ext) || file.originalname.endsWith('.tar.gz')) {
      cb(null, true);
    } else {
      cb(new Error('Only .zip and .tar.gz files are allowed'));
    }
  },
});

// GET /api/developer/stats
router.get('/stats', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const stats = await pluginService.getDeveloperStats(req.userId!);
    res.json({ success: true, data: stats });
  } catch (error) {
    next(error);
  }
});

// GET /api/developer/agents
router.get('/agents', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const agents = await agentService.getDeveloperAgents(req.userId!);
    res.json({ success: true, data: agents });
  } catch (error) {
    next(error);
  }
});

// POST /api/developer/agents/:id/upload
router.post('/agents/:id/upload', authenticate, requireDeveloper, upload.single('bundle'), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!req.file) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'No file uploaded' } });
      return;
    }
    const result = await pluginService.uploadAgentBundle(req.params.id, req.userId!, req.file.path);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// API Keys
// ============================================

// GET /api/developer/api-keys
router.get('/api-keys', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const keys = await pluginService.getDeveloperApiKeys(req.userId!);
    res.json({ success: true, data: keys });
  } catch (error) {
    next(error);
  }
});

// POST /api/developer/api-keys
router.post('/api-keys', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { name, permissions, expiresInDays } = req.body;
    const key = await pluginService.createApiKey(req.userId!, { name, permissions, expiresInDays });
    res.status(201).json({ success: true, data: key });
  } catch (error) {
    next(error);
  }
});

// DELETE /api/developer/api-keys/:id
router.delete('/api-keys/:id', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await pluginService.deleteApiKey(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Earnings
// ============================================

// GET /api/developer/earnings
router.get('/earnings', authenticate, requireDeveloper, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Return credit-based earnings summary
    const prisma = (await import('../models')).default;
    const userId = req.userId!;
    
    // Count credits earned from agent sales
    const salesCredits = await prisma.creditLedger.aggregate({
      where: { userId, reason: 'AGENT_SALE', amount: { gt: 0 } },
      _sum: { amount: true },
    });
    
    // Count credits earned from community upvotes
    const communityCredits = await prisma.creditLedger.aggregate({
      where: { userId, reason: { in: ['UPVOTE_RECEIVED'] }, amount: { gt: 0 } },
      _sum: { amount: true },
    });
    
    res.json({
      success: true,
      data: {
        totalEarnings: (salesCredits._sum.amount || 0) + (communityCredits._sum.amount || 0),
        agentSales: salesCredits._sum.amount || 0,
        communityEarnings: communityCredits._sum.amount || 0,
      },
    });
  } catch (error) {
    next(error);
  }
});

export default router;
