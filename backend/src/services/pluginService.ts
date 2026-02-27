import prisma from '../models';
import { NotFoundError, ForbiddenError } from '../middleware/errorHandler';
import { generateApiKey, hashApiKey } from '../utils/crypto';
import { logger } from '../utils/logger';

export class PluginService {
  async getDeveloperApiKeys(userId: string) {
    const keys = await prisma.developerApiKey.findMany({
      where: { userId },
      select: {
        id: true,
        name: true,
        keyPrefix: true,
        permissions: true,
        lastUsedAt: true,
        expiresAt: true,
        createdAt: true,
      },
      orderBy: { createdAt: 'desc' },
    });
    return keys.map((k) => ({
      ...k,
      permissions: JSON.parse(k.permissions),
    }));
  }

  async createApiKey(userId: string, data: { name: string; permissions?: string[]; expiresInDays?: number }) {
    const { key, hash, prefix } = generateApiKey();

    const expiresAt = data.expiresInDays
      ? new Date(Date.now() + data.expiresInDays * 86400000)
      : null;

    await prisma.developerApiKey.create({
      data: {
        userId,
        name: data.name,
        keyHash: hash,
        keyPrefix: prefix,
        permissions: JSON.stringify(data.permissions || ['read', 'write']),
        expiresAt,
      },
    });

    logger.info(`API key created for developer: ${userId}`);

    // Return the full key only once
    return { key, prefix, name: data.name };
  }

  async deleteApiKey(keyId: string, userId: string) {
    const key = await prisma.developerApiKey.findUnique({ where: { id: keyId } });
    if (!key) throw new NotFoundError('API Key');
    if (key.userId !== userId) throw new ForbiddenError('Not your API key');

    await prisma.developerApiKey.delete({ where: { id: keyId } });
    logger.info(`API key deleted: ${keyId}`);
  }

  async getDeveloperStats(developerId: string) {
    const [agentCount, totalDownloads, totalRevenue, totalReviews] = await Promise.all([
      prisma.agent.count({ where: { developerId } }),
      prisma.agent.aggregate({
        where: { developerId },
        _sum: { downloads: true },
      }),
      prisma.purchase.aggregate({
        where: { agent: { developerId }, status: 'COMPLETED' },
        _sum: { creditCost: true },
      }),
      prisma.agentReview.count({
        where: { agent: { developerId } },
      }),
    ]);

    return {
      agentCount,
      totalDownloads: totalDownloads._sum.downloads || 0,
      totalRevenue: totalRevenue._sum?.creditCost || 0,
      totalReviews,
    };
  }

  async uploadAgentBundle(agentId: string, developerId: string, filePath: string) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');
    if (agent.developerId !== developerId) throw new ForbiddenError('Not your agent');

    const updated = await prisma.agent.update({
      where: { id: agentId },
      data: { bundlePath: filePath },
    });

    // Create version record
    await prisma.agentVersion.create({
      data: {
        agentId,
        version: agent.version,
        bundlePath: filePath,
      },
    });

    logger.info(`Agent bundle uploaded: ${agentId} -> ${filePath}`);
    return updated;
  }
}

export const pluginService = new PluginService();
