import { Router, Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { authenticate, AuthRequest } from '../middleware/auth';
import { validate } from '../middleware/validation';
import { registerSchema, loginSchema } from '../utils/validators';
import { authService } from '../services/authService';
import { config } from '../config';
import nodemailer from 'nodemailer';

const router = Router();

// POST /api/auth/register
router.post('/register', validate(registerSchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.register(req.body);
    res.status(201).json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/verify-email
router.post('/verify-email', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { email, code } = req.body;
    if (!email || !code) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Email and code are required' } });
      return;
    }
    const result = await authService.verifyEmail(email, code);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/resend-verification
router.post('/resend-verification', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { email } = req.body;
    if (!email) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Email is required' } });
      return;
    }
    const result = await authService.resendVerification(email);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/login
router.post('/login', validate(loginSchema), async (req: Request, res: Response, next: NextFunction) => {
  try {
    const result = await authService.login(req.body.email, req.body.password);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/refresh
router.post('/refresh', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { refreshToken } = req.body;
    if (!refreshToken) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Refresh token required' } });
      return;
    }
    const tokens = await authService.refreshToken(refreshToken);
    res.json({ success: true, data: tokens });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/logout
router.post('/logout', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { refreshToken } = req.body;
    if (refreshToken) await authService.logout(refreshToken);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// GET /api/auth/me
router.get('/me', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const user = await authService.getProfile(req.userId!);
    res.json({ success: true, data: user });
  } catch (error) {
    next(error);
  }
});

// PUT /api/auth/profile
router.put('/profile', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Whitelist allowed profile fields to prevent privilege escalation
    const { displayName, bio, avatarUrl } = req.body;
    const safeData: Record<string, any> = {};
    if (displayName !== undefined) safeData.displayName = String(displayName).slice(0, 100);
    if (bio !== undefined) safeData.bio = String(bio).slice(0, 500);
    if (avatarUrl !== undefined) safeData.avatarUrl = String(avatarUrl).slice(0, 500);
    const user = await authService.updateProfile(req.userId!, safeData);
    res.json({ success: true, data: user });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/upgrade-developer
router.post('/upgrade-developer', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const user = await authService.upgradeToDeveloper(req.userId!);
    res.json({ success: true, data: user });
  } catch (error) {
    next(error);
  }
});

// POST /api/auth/test-smtp — verify SMTP connection
router.post('/test-smtp', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (!config.smtp.user || !config.smtp.pass) {
      return res.json({ success: false, message: 'SMTP credentials not configured. Set SMTP settings in the desktop app Settings → Email tab.' });
    }
    const transporter = nodemailer.createTransport({
      host: config.smtp.host,
      port: config.smtp.port,
      secure: config.smtp.secure,
      auth: { user: config.smtp.user, pass: config.smtp.pass },
    });
    await transporter.verify();
    res.json({ success: true, message: 'SMTP connection verified successfully.' });
  } catch (error: any) {
    res.json({ success: false, message: `SMTP test failed: ${error.message}` });
  }
});

// POST /api/auth/runtime-token — Long-lived token for agent runtime (central server mode)
router.post('/runtime-token', authenticate, async (req: AuthRequest, res: Response, _next: NextFunction) => {
  try {
    const token = jwt.sign(
      { userId: req.userId, role: 'SYSTEM' },
      config.jwt.secret,
      { expiresIn: '30d' },
    );
    res.json({ success: true, data: { runtimeToken: token } });
  } catch (error: any) {
    res.status(500).json({ success: false, error: { code: 'INTERNAL_ERROR', message: error.message } });
  }
});

export default router;
