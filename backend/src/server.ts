import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
// @ts-ignore
import rateLimit from 'express-rate-limit';
import { createServer } from 'http';
import path from 'path';
import fs from 'fs';

import { config } from './config';
import { logger } from './utils/logger';
import { errorHandler } from './middleware/errorHandler';
import { initWebSocket } from './services/websocketService';

// Routes
import authRoutes from './routes/auth';
import agentRoutes from './routes/agents';
import executionRoutes from './routes/execution';
import settingsRoutes from './routes/settings';
import developerRoutes from './routes/developer';

import communityRoutes from './routes/community';
import creditsRoutes from './routes/credits';
import exchangeRoutes from './routes/exchange';
import subscriptionRoutes from './routes/subscriptions';
import stripeRoutes from './routes/stripe';
import socialRoutes from './routes/social';
import electionRoutes from './routes/election';
import ownerChatRoutes from './routes/ownerChat';
import ideRoutes from './routes/ide';

const app = express();
const server = createServer(app);

// ============================================
// Middleware
// ============================================

// CORS
app.use(cors({
  origin: (origin: string | undefined, callback: (err: Error | null, allow?: boolean) => void) => {
    if (!origin) return callback(null, true);
    const allowed = config.cors.origins;
    if (allowed.includes('*') || allowed.includes(origin) || origin.startsWith('http://localhost')) {
      return callback(null, true);
    }
    callback(null, false);
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Runtime-Secret', 'X-Runtime-Token'],
}));

// Security headers
app.use(helmet({
  crossOriginResourcePolicy: { policy: 'cross-origin' },
}));

// Rate limiting — skip for internal runtime requests (they use X-Runtime-Secret)
const limiter = rateLimit({
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.max,
  standardHeaders: true,
  legacyHeaders: false,
  skip: (req: any) => !!(req.headers['x-runtime-secret'] || req.headers['x-runtime-token']),
  message: { success: false, error: { code: 'RATE_LIMIT', message: 'Too many requests' } },
});
app.use('/api/', limiter);

// Stricter rate limiting for auth endpoints to prevent brute force
const authLimiter = rateLimit({
  windowMs: 60000, // 1 minute
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { success: false, error: { code: 'RATE_LIMIT', message: 'Too many auth requests. Please try again later.' } },
});
app.use('/api/auth/login', authLimiter);
app.use('/api/auth/register', authLimiter);
app.use('/api/auth/resend-verification', authLimiter);

// Parse raw body for Stripe webhook (must come before json parser)
app.use('/api/stripe/webhook', express.raw({ type: 'application/json' }));

// Parse JSON for all routes
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Static files for uploads
const uploadDir = path.resolve(config.upload.dir);
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}
app.use('/uploads', express.static(uploadDir, {
  setHeaders: (res, filePath) => {
    // Prevent stored XSS via uploaded SVG/HTML — force downloads for dangerous types
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Security-Policy', "default-src 'none'; img-src 'self'; style-src 'none'; script-src 'none'");

    // Force download for file types that could execute scripts when rendered inline
    const dangerousExts = /\.(svg|html?|xml|xhtml|xsl|xslt|mht|mhtml)$/i;
    if (dangerousExts.test(filePath)) {
      res.setHeader('Content-Disposition', 'attachment');
      res.setHeader('Content-Type', 'application/octet-stream');
    }
  },
}));

// Ensure log directory exists
const logDir = path.resolve(config.logging.dir);
if (!fs.existsSync(logDir)) {
  fs.mkdirSync(logDir, { recursive: true });
}

// ============================================
// Routes
// ============================================

app.use('/api/auth', authRoutes);
app.use('/api/agents', agentRoutes);
app.use('/api/execution', executionRoutes);
app.use('/api/community', communityRoutes);
app.use('/api/credits', creditsRoutes);
app.use('/api/exchange', exchangeRoutes);
app.use('/api/stripe', stripeRoutes);
app.use('/api/subscriptions', subscriptionRoutes);
app.use('/api/settings', settingsRoutes);
app.use('/api/developer', developerRoutes);
app.use('/api/social', socialRoutes);
app.use('/api/election', electionRoutes);
app.use('/api/owner-chat', ownerChatRoutes);
app.use('/api/ide', ideRoutes);

// Health check
app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

// 404 handler
app.use((_req, res) => {
  res.status(404).json({
    success: false,
    error: { code: 'NOT_FOUND', message: 'Endpoint not found' },
  });
});

// Error handler
app.use(errorHandler);

// ============================================
// WebSocket
// ============================================

initWebSocket(server);

// ============================================
// Start Server
// ============================================

async function ensureDemoAccounts() {
  try {
    const prisma = (await import('./models')).default;
    const bcrypt = (await import('bcryptjs')).default;

    // NOTE: Legacy fake-purchase cleanup removed — it was deleting 
    // real user purchases for S+ agents on every startup.

    const demoAccounts = [
      { email: 'admin@ogenti.app', username: 'admin', displayName: 'Platform Admin', password: 'admin123456', role: 'ADMIN', bio: 'Platform administrator' },
      { email: 'dev@ogenti.app', username: 'dev', displayName: 'Developer', password: 'developer123', role: 'DEVELOPER', bio: 'Default developer account' },
    ];

    for (const acct of demoAccounts) {
      const existing = await prisma.user.findUnique({ where: { email: acct.email } });

      if (!existing) {
        const passwordHash = await bcrypt.hash(acct.password, 12);
        await prisma.user.create({
          data: {
            email: acct.email,
            username: acct.username,
            displayName: acct.displayName,
            passwordHash,
            role: acct.role,
            emailVerified: true,
            bio: acct.bio,
            settings: { create: {} },
          },
        });
        logger.info(`Demo account created: ${acct.email}`);
      } else {
        logger.info(`Demo account already exists: ${acct.email} (password not reset)`);
      }
    }
  } catch (err: any) {
    logger.warn(`Demo account seed skipped: ${err.message}`);
  }
}

server.listen(config.port, async () => {
  logger.info(`🚀 Server running on port ${config.port}`);
  logger.info(`📡 Environment: ${config.env}`);
  logger.info(`🔗 Frontend URL: ${config.frontendUrl}`);
  logger.info(`🔗 Backend URL: ${config.backendUrl}`);
  logger.info(`🤖 Agent Runtime URL: ${config.agentRuntime.url}`);

  // Start periodic hot score refresh for the feed algorithm
  try {
    const { feedAlgorithmService } = await import('./services/feedAlgorithmService');
    feedAlgorithmService.startPeriodicRefresh(5); // every 5 minutes
    logger.info('📊 Feed algorithm: hot score refresh started');
  } catch (err: any) {
    logger.warn(`Feed algorithm startup failed: ${err.message}`);
  }

  // Ensure demo accounts exist ONLY in non-production environments
  if (config.env !== 'production') {
    await ensureDemoAccounts();
  }

  // Backfill social profiles for any purchases missing them
  try {
    const { socialService } = await import('./services/socialService');
    const prismaDB = (await import('./models')).default;
    const purchases = await prismaDB.purchase.findMany({
      where: { status: 'COMPLETED' },
      select: { id: true, userId: true, agentId: true },
    });
    const profiles = await prismaDB.agentProfile.findMany({
      select: { purchaseId: true },
    });
    const existing = new Set(profiles.map((p: any) => p.purchaseId));
    const missing = purchases.filter((p: any) => !existing.has(p.id));
    if (missing.length > 0) {
      let created = 0;
      for (const m of missing) {
        try {
          await socialService.createProfile(m.id, m.userId, m.agentId);
          created++;
        } catch {}
      }
      logger.info(`🔗 Social backfill: ${created}/${missing.length} profiles created`);
    }
  } catch (err: any) {
    logger.warn(`Social profile backfill skipped: ${err.message}`);
  }
});

// Graceful shutdown
process.on('SIGINT', async () => {
  logger.info('Shutting down gracefully...');
  try {
    const prisma = (await import('./models')).default;
    await prisma.$disconnect();
    logger.info('Prisma disconnected');
  } catch (e) {
    // ignore
  }
  server.close(() => {
    logger.info('Server closed');
    process.exit(0);
  });
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', { promise, reason });
});

export { app, server };
