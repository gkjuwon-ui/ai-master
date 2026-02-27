import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import ms from 'ms';
import { v4 as uuid } from 'uuid';
import prisma from '../models';
import { config } from '../config';
import { AppError, ConflictError, NotFoundError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { emailService } from './emailService';

interface TokenPayload {
  userId: string;
  role: string;
}

/** Check if SMTP is properly configured for email verification */
function isSmtpConfigured(): boolean {
  return !!(config.smtp.user && config.smtp.pass);
}

export class AuthService {
  /** Generate a 6-digit verification code using cryptographic randomness */
  private generateVerificationCode(): string {
    const crypto = require('crypto');
    return crypto.randomInt(100000, 999999).toString();
  }

  async register(data: {
    email: string;
    username: string;
    password: string;
    displayName: string;
  }) {
    const existingEmail = await prisma.user.findUnique({ where: { email: data.email } });
    if (existingEmail) {
      // If existing user hasn't verified email, allow re-sending verification
      if (!existingEmail.emailVerified) {
        // Update password & display name in case user changed them
        const passwordHash = await bcrypt.hash(data.password, 12);
        await prisma.user.update({
          where: { id: existingEmail.id },
          data: { passwordHash, displayName: data.displayName },
        });
        // Desktop mode: auto-verify existing unverified user
        if (!isSmtpConfigured()) {
          const verifiedUser = await prisma.user.update({
            where: { id: existingEmail.id },
            data: { emailVerified: true },
            select: {
              id: true, email: true, username: true, displayName: true,
              avatar: true, role: true, createdAt: true, updatedAt: true,
            },
          });
          const tokens = await this.generateTokens({ userId: verifiedUser.id, role: verifiedUser.role });
          return { user: verifiedUser, tokens, autoVerified: true };
        }
        await this.sendVerificationCode(existingEmail.id, data.email, data.displayName);
        return {
          message: 'Verification code sent to your email.',
          requiresVerification: true,
          email: data.email,
        };
      }
      // Desktop mode: if email already verified, just log them in
      if (!isSmtpConfigured()) {
        const passwordMatch = await bcrypt.compare(data.password, existingEmail.passwordHash);
        if (passwordMatch) {
          const tokens = await this.generateTokens({ userId: existingEmail.id, role: existingEmail.role });
          const userObj = await prisma.user.findUnique({
            where: { id: existingEmail.id },
            select: { id: true, email: true, username: true, displayName: true, avatar: true, role: true, createdAt: true, updatedAt: true },
          });
          return { user: userObj, tokens, autoVerified: true };
        }
      }
      throw new ConflictError('Email already registered');
    }

    // Auto-resolve username collisions by appending random suffix
    let finalUsername = data.username;
    let existingUsername = await prisma.user.findUnique({ where: { username: finalUsername } });
    if (existingUsername) {
      for (let i = 0; i < 10; i++) {
        const suffix = Math.floor(Math.random() * 10000);
        finalUsername = `${data.username.slice(0, 25)}_${suffix}`;
        existingUsername = await prisma.user.findUnique({ where: { username: finalUsername } });
        if (!existingUsername) break;
      }
      if (existingUsername) throw new ConflictError('Username already taken — please try a different email');
    }

    const passwordHash = await bcrypt.hash(data.password, 12);

    const user = await prisma.user.create({
      data: {
        email: data.email,
        username: finalUsername,
        displayName: data.displayName,
        passwordHash,
        emailVerified: false,
        credits: 5, // Signup bonus (reduced for economy balance)
        settings: {
          create: {},
        },
      },
      select: {
        id: true,
        email: true,
        username: true,
        displayName: true,
        role: true,
      },
    });

    // Record signup bonus in credit ledger
    try {
      const { creditService } = await import('./creditService');
      await creditService.grantSignupBonus(user.id);
    } catch (err: any) {
      logger.warn(`Failed to grant signup bonus: ${err.message}`);
    }

    // Desktop mode (no SMTP): auto-verify and return tokens so no code is ever shown
    if (!isSmtpConfigured()) {
      const verifiedUser = await prisma.user.update({
        where: { id: user.id },
        data: { emailVerified: true },
        select: {
          id: true, email: true, username: true, displayName: true,
          avatar: true, role: true, createdAt: true, updatedAt: true,
        },
      });
      const tokens = await this.generateTokens({ userId: verifiedUser.id, role: verifiedUser.role });
      logger.info(`User registered & auto-verified (desktop mode): ${verifiedUser.email}`);
      return {
        user: verifiedUser,
        tokens,
        autoVerified: true,
      };
    }

    // Cloud mode: send verification code via email
    await this.sendVerificationCode(user.id, data.email, data.displayName);

    logger.info(`User registered (pending verification): ${user.email}`);

    return {
      message: 'Verification code sent to your email.',
      requiresVerification: true,
      email: data.email,
    };
  }

  private async sendVerificationCode(userId: string, email: string, displayName: string): Promise<string> {
    // Delete any existing tokens for this email
    await prisma.emailVerificationToken.deleteMany({ where: { email } });

    const code = this.generateVerificationCode();
    const expiresAt = new Date();
    expiresAt.setMinutes(expiresAt.getMinutes() + 10); // 10 minutes expiry

    await prisma.emailVerificationToken.create({
      data: {
        email,
        code,
        userId,
        expiresAt,
      },
    });

    const sent = await emailService.sendVerificationEmail(email, code, displayName);
    if (!sent) {
      throw new AppError('Failed to send verification email. Please try again later.', 500, 'EMAIL_SEND_FAILED');
    }

    return code;
  }

  async verifyEmail(email: string, code: string) {
    const token = await prisma.emailVerificationToken.findFirst({
      where: { email, code },
    });

    if (!token) {
      throw new AppError('Invalid verification code.', 400, 'INVALID_CODE');
    }

    if (token.expiresAt < new Date()) {
      await prisma.emailVerificationToken.delete({ where: { id: token.id } });
      throw new AppError('Verification code has expired. Please request a new one.', 400, 'CODE_EXPIRED');
    }

    // Mark email as verified
    const user = await prisma.user.update({
      where: { id: token.userId },
      data: { emailVerified: true },
      select: {
        id: true,
        email: true,
        username: true,
        displayName: true,
        avatar: true,
        role: true,
        createdAt: true,
        updatedAt: true,
      },
    });

    // Clean up verification tokens
    await prisma.emailVerificationToken.deleteMany({ where: { email } });

    // Generate tokens so user is logged in after verification
    const tokens = await this.generateTokens({ userId: user.id, role: user.role });

    logger.info(`Email verified: ${user.email}`);

    return { user, tokens };
  }

  async resendVerification(email: string) {
    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) throw new NotFoundError('User');
    if (user.emailVerified) {
      throw new AppError('Email is already verified.', 400, 'ALREADY_VERIFIED');
    }

    // Rate limiting: check if last token was created within 60 seconds
    const recentToken = await prisma.emailVerificationToken.findFirst({
      where: { email },
      orderBy: { createdAt: 'desc' },
    });
    if (recentToken) {
      const timeSince = Date.now() - recentToken.createdAt.getTime();
      if (timeSince < 60000) {
        throw new AppError('Please wait before requesting a new code.', 429, 'RATE_LIMITED');
      }
    }

    // Desktop mode: auto-verify instead of resending
    if (!isSmtpConfigured()) {
      await prisma.user.update({ where: { id: user.id }, data: { emailVerified: true } });
      return { message: 'Auto-verified (desktop mode).', autoVerified: true };
    }
    await this.sendVerificationCode(user.id, email, user.displayName);
    return { message: 'Verification code re-sent.' };
  }

  async login(email: string, password: string) {
    // Auto-seed: if no users exist at all, create default admin+dev accounts
    // Only in non-production environments
    const userCount = await prisma.user.count();
    if (userCount === 0 && process.env.NODE_ENV !== 'production') {
      logger.info('No users found — auto-seeding default accounts (non-production)');
      const adminHash = await bcrypt.hash('admin123456', 12);
      const devHash = await bcrypt.hash('developer123', 12);
      await prisma.user.create({
        data: {
          email: 'admin@ogenti.app', username: 'admin', displayName: 'Platform Admin',
          passwordHash: adminHash, role: 'ADMIN', emailVerified: true, bio: 'Platform administrator',
          settings: { create: {} },
        },
      });
      await prisma.user.create({
        data: {
          email: 'dev@ogenti.app', username: 'dev', displayName: 'Developer',
          passwordHash: devHash, role: 'DEVELOPER', emailVerified: true, bio: 'Default developer account',
          settings: { create: {} },
        },
      });
      logger.info('Auto-seeded admin@ogenti.app and dev@ogenti.app');
    }

    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) throw new AppError('Invalid credentials', 401, 'INVALID_CREDENTIALS');

    const isValid = await bcrypt.compare(password, user.passwordHash);
    if (!isValid) throw new AppError('Invalid credentials', 401, 'INVALID_CREDENTIALS');

    // Email verification enforcement
    if (!user.emailVerified) {
      // Desktop mode (no SMTP): auto-verify and proceed
      if (!isSmtpConfigured()) {
        await prisma.user.update({
          where: { id: user.id },
          data: { emailVerified: true },
        });
        logger.info(`User auto-verified on login (desktop mode): ${user.email}`);
      } else {
        // Cloud mode: require email verification
        await this.sendVerificationCode(user.id, user.email, user.displayName);
        const errorData: any = {
          message: 'Email not verified. A verification code has been sent.',
          code: 'EMAIL_NOT_VERIFIED',
          email: user.email,
        };
        const err = new AppError(errorData.message, 403, 'EMAIL_NOT_VERIFIED');
        (err as any).data = errorData;
        throw err;
      }
    }

    const tokens = await this.generateTokens({ userId: user.id, role: user.role });
    logger.info(`User logged in: ${user.email}`);

    return {
      user: {
        id: user.id,
        email: user.email,
        username: user.username,
        displayName: user.displayName,
        avatar: user.avatar,
        role: user.role,
        createdAt: user.createdAt.toISOString(),
        updatedAt: user.updatedAt.toISOString(),
      },
      tokens,
    };
  }

  async refreshToken(refreshTokenStr: string) {
    const storedToken = await prisma.refreshToken.findUnique({
      where: { token: refreshTokenStr },
    });

    if (!storedToken || storedToken.expiresAt < new Date()) {
      if (storedToken) {
        await prisma.refreshToken.delete({ where: { id: storedToken.id } });
      }
      throw new AppError('Invalid refresh token', 401, 'INVALID_REFRESH_TOKEN');
    }

    try {
      const decoded = jwt.verify(refreshTokenStr, config.jwt.refreshSecret) as TokenPayload;
      await prisma.refreshToken.delete({ where: { id: storedToken.id } });
      const tokens = await this.generateTokens({ userId: decoded.userId, role: decoded.role });
      return tokens;
    } catch {
      await prisma.refreshToken.delete({ where: { id: storedToken.id } });
      throw new AppError('Invalid refresh token', 401, 'INVALID_REFRESH_TOKEN');
    }
  }

  async logout(refreshTokenStr: string) {
    await prisma.refreshToken.deleteMany({ where: { token: refreshTokenStr } });
  }

  async getProfile(userId: string) {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      select: {
        id: true,
        email: true,
        username: true,
        displayName: true,
        avatar: true,
        role: true,
        bio: true,
        website: true,
        credits: true,
        createdAt: true,
        updatedAt: true,
      },
    });
    if (!user) throw new NotFoundError('User');
    return user;
  }

  async updateProfile(userId: string, data: { displayName?: string; bio?: string; website?: string; avatar?: string }) {
    const user = await prisma.user.update({
      where: { id: userId },
      data,
      select: {
        id: true,
        email: true,
        username: true,
        displayName: true,
        avatar: true,
        role: true,
        bio: true,
        website: true,
        createdAt: true,
        updatedAt: true,
      },
    });
    return user;
  }

  async upgradeToDeveloper(userId: string) {
    const user = await prisma.user.update({
      where: { id: userId },
      data: { role: 'DEVELOPER' },
    });
    return user;
  }

  private async generateTokens(payload: TokenPayload) {
    const accessToken = jwt.sign(payload, config.jwt.secret, {
      expiresIn: config.jwt.expiresIn,
    } as jwt.SignOptions);

    const refreshToken = jwt.sign(payload, config.jwt.refreshSecret, {
      expiresIn: config.jwt.refreshExpiresIn,
    } as jwt.SignOptions);

    // Store refresh token
    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + 7);

    await prisma.refreshToken.create({
      data: {
        token: refreshToken,
        userId: payload.userId,
        expiresAt,
      },
    });

    return {
      accessToken,
      refreshToken,
      expiresIn: Math.floor((ms(config.jwt.expiresIn as ms.StringValue) as number) / 1000), // derived from config
    };
  }
}

export const authService = new AuthService();
