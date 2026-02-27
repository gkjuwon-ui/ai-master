import { Router, Response, NextFunction } from 'express';
import { authenticate, AuthRequest } from '../middleware/auth';
import { validate } from '../middleware/validation';
import { llmConfigSchema, settingsUpdateSchema } from '../utils/validators';
import { llmService } from '../services/llmService';
import { settingsService } from '../services/settingsService';

const router = Router();

// ============================================
// LLM Configuration
// ============================================

// GET /api/settings/llm/providers
router.get('/llm/providers', (_req, res) => {
  const providers = llmService.getAvailableProviders();
  res.json({ success: true, data: providers });
});

// GET /api/settings/llm/configs
router.get('/llm/configs', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const configs = await llmService.getUserConfigs(req.userId!);
    res.json({ success: true, data: configs });
  } catch (error) {
    next(error);
  }
});

// POST /api/settings/llm/configs
router.post('/llm/configs', authenticate, validate(llmConfigSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const llmConfig = await llmService.saveConfig(req.userId!, req.body);
    res.status(201).json({ success: true, data: llmConfig });
  } catch (error) {
    next(error);
  }
});

// PUT /api/settings/llm/configs/:id
router.put('/llm/configs/:id', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const llmConfig = await llmService.updateConfig(req.params.id, req.userId!, req.body);
    res.json({ success: true, data: llmConfig });
  } catch (error) {
    next(error);
  }
});

// DELETE /api/settings/llm/configs/:id
router.delete('/llm/configs/:id', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await llmService.deleteConfig(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/settings/llm/configs/:id/test
router.post('/llm/configs/:id/test', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await llmService.testConfig(req.params.id, req.userId!);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// User Settings
// ============================================

// GET /api/settings
router.get('/', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const settings = await settingsService.getSettings(req.userId!);
    res.json({ success: true, data: settings });
  } catch (error) {
    next(error);
  }
});

// PUT /api/settings
router.put('/', authenticate, validate(settingsUpdateSchema), async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const settings = await settingsService.updateSettings(req.userId!, req.body);
    res.json({ success: true, data: settings });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Notifications
// ============================================

// GET /api/settings/notifications
router.get('/notifications', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const page = parseInt(req.query.page as string) || 1;
    const result = await settingsService.getNotifications(req.userId!, page);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// PUT /api/settings/notifications/:id/read
router.put('/notifications/:id/read', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await settingsService.markNotificationRead(req.params.id, req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// POST /api/settings/notifications/read-all
router.post('/notifications/read-all', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    await settingsService.markAllNotificationsRead(req.userId!);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

export default router;
