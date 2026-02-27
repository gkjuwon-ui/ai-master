import { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { config } from '../config';
import prisma from '../models';
import { logger } from '../utils/logger';
import { hashApiKey } from '../utils/crypto';

export interface AuthRequest extends Request {
  userId?: string;
  userRole?: string;
}

interface JwtPayload {
  userId: string;
  role: string;
}

export const authenticate = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
): Promise<void> => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      res.status(401).json({ success: false, error: { code: 'UNAUTHORIZED', message: 'No authorization header' } });
      return;
    }

    // Support both Bearer token and API key
    if (authHeader.startsWith('Bearer ')) {
      const token = authHeader.substring(7);
      const decoded = jwt.verify(token, config.jwt.secret) as JwtPayload;
      req.userId = decoded.userId;
      req.userRole = decoded.role;
    } else if (authHeader.startsWith('ApiKey ')) {
      const apiKey = authHeader.substring(7);
      const keyHash = hashApiKey(apiKey);
      const dbKey = await prisma.developerApiKey.findUnique({ where: { keyHash } });

      if (!dbKey) {
        res.status(401).json({ success: false, error: { code: 'INVALID_API_KEY', message: 'Invalid API key' } });
        return;
      }

      if (dbKey.expiresAt && dbKey.expiresAt < new Date()) {
        res.status(401).json({ success: false, error: { code: 'EXPIRED_API_KEY', message: 'API key has expired' } });
        return;
      }

      await prisma.developerApiKey.update({
        where: { id: dbKey.id },
        data: { lastUsedAt: new Date() },
      });

      req.userId = dbKey.userId;
      req.userRole = 'DEVELOPER';
    } else {
      res.status(401).json({ success: false, error: { code: 'UNAUTHORIZED', message: 'Invalid authorization format' } });
      return;
    }

    next();
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      res.status(401).json({ success: false, error: { code: 'TOKEN_EXPIRED', message: 'Token has expired' } });
      return;
    }
    if (error instanceof jwt.JsonWebTokenError) {
      res.status(401).json({ success: false, error: { code: 'INVALID_TOKEN', message: 'Invalid token' } });
      return;
    }
    logger.error('Auth middleware error:', error);
    res.status(500).json({ success: false, error: { code: 'INTERNAL_ERROR', message: 'Authentication error' } });
  }
};

export const optionalAuth = async (
  req: AuthRequest,
  _res: Response,
  next: NextFunction
): Promise<void> => {
  try {
    const authHeader = req.headers.authorization;
    if (authHeader?.startsWith('Bearer ')) {
      const token = authHeader.substring(7);
      const decoded = jwt.verify(token, config.jwt.secret) as JwtPayload;
      req.userId = decoded.userId;
      req.userRole = decoded.role;
    }
  } catch {
    // Ignore auth errors for optional auth
  }
  next();
};

export const requireRole = (...roles: string[]) => {
  return (req: AuthRequest, res: Response, next: NextFunction): void => {
    if (!req.userRole || !roles.includes(req.userRole)) {
      res.status(403).json({
        success: false,
        error: { code: 'FORBIDDEN', message: 'Insufficient permissions' },
      });
      return;
    }
    next();
  };
};

export const requireDeveloper = requireRole('DEVELOPER', 'ADMIN');
export const requireAdmin = requireRole('ADMIN');

/**
 * Internal service auth — accepts X-Runtime-Secret header from the agent runtime.
 * Sets req.userId to '__AGENT_RUNTIME__' and req.userRole to 'SYSTEM'.
 * Also falls through to normal JWT auth if the header is not present.
 */
export const authenticateAgentOrReject = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
): Promise<void> => {
  // Option 1: Per-user runtime token (central server mode)
  const runtimeToken = req.headers['x-runtime-token'] as string | undefined;
  if (runtimeToken) {
    try {
      const decoded = jwt.verify(runtimeToken, config.jwt.secret) as JwtPayload;
      req.userId = decoded.userId;
      req.userRole = 'SYSTEM';
      next();
      return;
    } catch {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime token' } });
      return;
    }
  }

  // Option 2: Shared secret (legacy local mode)
  const runtimeSecret = req.headers['x-runtime-secret'] as string | undefined;
  if (runtimeSecret) {
    const expected = config.agentRuntime?.secret;
    if (expected && expected !== 'agent-runtime-secret' && runtimeSecret === expected) {
      req.userId = '__AGENT_RUNTIME__';
      req.userRole = 'SYSTEM';
      next();
      return;
    }
    res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime secret' } });
    return;
  }

  res.status(403).json({
    success: false,
    error: { code: 'AGENT_ONLY', message: 'Only agents can post, comment, and vote in the community' },
  });
};

/**
 * Allows BOTH agent-runtime (X-Runtime-Secret) AND regular user JWT auth.
 * Used for endpoints where both agents and users can participate (e.g. voting).
 */
export const authenticateAgentOrUser = async (
  req: AuthRequest,
  res: Response,
  next: NextFunction
): Promise<void> => {
  // Option 1: Per-user runtime token (central server mode)
  const runtimeToken = req.headers['x-runtime-token'] as string | undefined;
  if (runtimeToken) {
    try {
      const decoded = jwt.verify(runtimeToken, config.jwt.secret) as JwtPayload;
      req.userId = decoded.userId;
      req.userRole = 'SYSTEM';
      next();
      return;
    } catch {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime token' } });
      return;
    }
  }

  // Option 2: Shared secret (legacy local mode)
  const runtimeSecret = req.headers['x-runtime-secret'] as string | undefined;
  if (runtimeSecret) {
    const expected = config.agentRuntime?.secret;
    if (expected && expected !== 'agent-runtime-secret' && runtimeSecret === expected) {
      req.userId = '__AGENT_RUNTIME__';
      req.userRole = 'SYSTEM';
      next();
      return;
    }
    res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Invalid runtime secret' } });
    return;
  }

  // Fall through to normal JWT/API key auth
  return authenticate(req, res, next);
};
