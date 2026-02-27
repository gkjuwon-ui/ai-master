import crypto from 'crypto';
import prisma from '../models';
import { NotFoundError, ForbiddenError, BadRequestError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

export class AgentService {
  async list(query: {
    page?: number;
    limit?: number;
    category?: string;
    search?: string;
    sortBy?: string;
    pricing?: string;
    priceMin?: number;
    priceMax?: number;
    tags?: string;
  }) {
    const page = query.page || 1;
    const limit = query.limit || 20;
    const skip = (page - 1) * limit;

    const where: any = { status: 'PUBLISHED' };

    if (query.category) where.category = query.category;
    if (query.pricing === 'free') where.price = 0;
    if (query.pricing === 'paid') where.price = { gt: 0 };
    if (query.search) {
      where.OR = [
        { name: { contains: query.search } },
        { description: { contains: query.search } },
        { tags: { contains: query.search } },
      ];
    }
    if (query.priceMin !== undefined) where.price = { ...where.price, gte: query.priceMin };
    if (query.priceMax !== undefined) where.price = { ...where.price, lte: query.priceMax };
    if (query.tags) {
      const tagList = query.tags.split(',');
      where.AND = tagList.map((tag: string) => ({ tags: { contains: tag.trim() } }));
    }

    let orderBy: any = {};
    switch (query.sortBy) {
      case 'recent': orderBy = { createdAt: 'desc' }; break;
      case 'rating': orderBy = { rating: 'desc' }; break;
      case 'price_asc': orderBy = { price: 'asc' }; break;
      case 'price_desc': orderBy = { price: 'desc' }; break;
      default: orderBy = { downloads: 'desc' };
    }

    const [agents, total] = await Promise.all([
      prisma.agent.findMany({
        where,
        skip,
        take: limit,
        orderBy,
        include: {
          developer: {
            select: { id: true, username: true, displayName: true, avatar: true },
          },
          screenshots: { orderBy: { order: 'asc' } },
        },
      }),
      prisma.agent.count({ where }),
    ]);

    return {
      agents: agents.map(this.formatAgent),
      total,
      page,
      limit,
      totalPages: Math.ceil(total / limit),
    };
  }

  async getById(id: string) {
    const agent = await prisma.agent.findUnique({
      where: { id },
      include: {
        developer: {
          select: { id: true, username: true, displayName: true, avatar: true },
        },
        screenshots: { orderBy: { order: 'asc' } },
        reviews: {
          include: { user: { select: { id: true, username: true, displayName: true, avatar: true } } },
          orderBy: { createdAt: 'desc' },
          take: 20,
        },
      },
    });
    if (!agent) throw new NotFoundError('Agent');
    return this.formatAgent(agent);
  }

  async getBySlug(slug: string) {
    const agent = await prisma.agent.findUnique({
      where: { slug },
      include: {
        developer: {
          select: { id: true, username: true, displayName: true, avatar: true },
        },
        screenshots: { orderBy: { order: 'asc' } },
        reviews: {
          include: { user: { select: { id: true, username: true, displayName: true, avatar: true } } },
          orderBy: { createdAt: 'desc' },
          take: 20,
        },
      },
    });
    if (!agent) throw new NotFoundError('Agent');
    return this.formatAgent(agent);
  }

  async create(developerId: string, data: any) {
    let slug = slugify(data.name);
    const existingSlug = await prisma.agent.findUnique({ where: { slug } });
    if (existingSlug) slug = `${slug}-${crypto.randomBytes(4).toString('hex')}`;

    const agent = await prisma.agent.create({
      data: {
        name: data.name,
        slug,
        description: data.description,
        longDescription: data.longDescription,
        category: data.category,
        tags: JSON.stringify(data.tags || []),
        capabilities: JSON.stringify(data.capabilities || []),
        price: data.price || 0,
        pricingModel: data.pricingModel || 'FREE',
        entryPoint: data.entryPoint || 'main.py',
        runtime: data.runtime || 'python',
        permissions: JSON.stringify(data.permissions || []),
        configSchema: data.configSchema ? JSON.stringify(data.configSchema) : null,
        inputSchema: data.inputSchema ? JSON.stringify(data.inputSchema) : null,
        outputSchema: data.outputSchema ? JSON.stringify(data.outputSchema) : null,
        developerId,
        status: 'DRAFT',
      },
      include: {
        developer: {
          select: { id: true, username: true, displayName: true, avatar: true },
        },
      },
    });

    logger.info(`Agent created: ${agent.name} by ${developerId}`);
    return this.formatAgent(agent);
  }

  async update(agentId: string, developerId: string, data: any) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');
    if (agent.developerId !== developerId) throw new ForbiddenError('Not the agent developer');

    const updateData: any = {};
    if (data.name) updateData.name = data.name;
    if (data.description) updateData.description = data.description;
    if (data.longDescription) updateData.longDescription = data.longDescription;
    if (data.category) updateData.category = data.category;
    if (data.tags) updateData.tags = JSON.stringify(data.tags);
    if (data.capabilities) updateData.capabilities = JSON.stringify(data.capabilities);
    if (data.price !== undefined) updateData.price = data.price;
    if (data.pricingModel) updateData.pricingModel = data.pricingModel;
    if (data.permissions) updateData.permissions = JSON.stringify(data.permissions);
    if (data.configSchema) updateData.configSchema = JSON.stringify(data.configSchema);

    const updated = await prisma.agent.update({
      where: { id: agentId },
      data: updateData,
      include: {
        developer: {
          select: { id: true, username: true, displayName: true, avatar: true },
        },
        screenshots: { orderBy: { order: 'asc' } },
      },
    });

    return this.formatAgent(updated);
  }

  async publish(agentId: string, developerId: string) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');
    if (agent.developerId !== developerId) throw new ForbiddenError('Not the agent developer');
    if (agent.status === 'PUBLISHED') throw new BadRequestError('Agent already published');

    // Set to PENDING_REVIEW while security review runs
    await prisma.agent.update({
      where: { id: agentId },
      data: { status: 'PENDING_REVIEW' },
    });

    logger.info(`Agent ${agent.name} submitted for security review`);

    // Run LLM + static security review
    try {
      const { agentReviewService } = await import('./agentReviewService');
      const report = await agentReviewService.reviewAgent(agentId, developerId);

      // Reload the agent (review service already updated the status)
      const updated = await prisma.agent.findUnique({
        where: { id: agentId },
        include: {
          developer: {
            select: { id: true, username: true, displayName: true, avatar: true },
          },
          screenshots: { orderBy: { order: 'asc' } },
        },
      });
      if (!updated) throw new NotFoundError('Agent');

      if (report.verdict === 'REJECTED') {
        throw new BadRequestError(
          `Agent rejected by security review: ${report.summary}`
        );
      }

      logger.info(`Agent published after review: ${agent.name}`);
      return this.formatAgent(updated);
    } catch (err: any) {
      // If it's already a BadRequestError (rejected), re-throw
      if (err.statusCode === 400 || err.message?.includes('rejected')) {
        throw err;
      }
      // On unexpected review failure, revert to DRAFT
      logger.error(`Security review error for ${agent.name}: ${err.message}`);
      await prisma.agent.update({
        where: { id: agentId },
        data: { status: 'DRAFT' },
      });
      throw new BadRequestError('Security review failed. Please try again later.');
    }
  }

  async unpublish(agentId: string, developerId: string) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');
    if (agent.developerId !== developerId) throw new ForbiddenError('Not the agent developer');

    return prisma.agent.update({
      where: { id: agentId },
      data: { status: 'DRAFT' },
    });
  }

  async delete(agentId: string, developerId: string) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');
    if (agent.developerId !== developerId) throw new ForbiddenError('Not the agent developer');

    await prisma.agent.delete({ where: { id: agentId } });
    logger.info(`Agent deleted: ${agent.name}`);
  }

  async getDeveloperAgents(developerId: string) {
    const agents = await prisma.agent.findMany({
      where: { developerId },
      include: {
        developer: {
          select: { id: true, username: true, displayName: true, avatar: true },
        },
        screenshots: { orderBy: { order: 'asc' } },
      },
      orderBy: { createdAt: 'desc' },
    });
    return agents.map(this.formatAgent);
  }

  async addReview(agentId: string, userId: string, data: { rating: number; title: string; content: string }) {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) throw new NotFoundError('Agent');

    // Check if user purchased the agent
    const purchase = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId, agentId } },
    });
    if (!purchase && agent.price > 0) {
      throw new ForbiddenError('Must purchase agent before reviewing');
    }

    const review = await prisma.agentReview.upsert({
      where: { agentId_userId: { agentId, userId } },
      create: { agentId, userId, rating: data.rating, title: data.title, content: data.content },
      update: { rating: data.rating, title: data.title, content: data.content },
      include: {
        user: { select: { id: true, username: true, displayName: true, avatar: true } },
      },
    });

    // Update agent rating
    const stats = await prisma.agentReview.aggregate({
      where: { agentId },
      _avg: { rating: true },
      _count: { rating: true },
    });

    await prisma.agent.update({
      where: { id: agentId },
      data: {
        rating: stats._avg.rating || 0,
        reviewCount: stats._count.rating,
      },
    });

    return review;
  }

  async getReviews(agentId: string, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const [reviews, total] = await Promise.all([
      prisma.agentReview.findMany({
        where: { agentId },
        include: {
          user: { select: { id: true, username: true, displayName: true, avatar: true } },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.agentReview.count({ where: { agentId } }),
    ]);
    return { reviews, total, page, limit, totalPages: Math.ceil(total / limit) };
  }

  async getPurchasedAgents(userId: string) {
    const purchases = await prisma.purchase.findMany({
      where: { userId, status: 'COMPLETED' },
      include: {
        agent: {
          include: {
            developer: {
              select: { id: true, username: true, displayName: true, avatar: true },
            },
          },
        },
      },
      orderBy: { createdAt: 'desc' },
    });
    return purchases.map((p) => ({
      ...p,
      agent: this.formatAgent(p.agent),
    }));
  }

  async hasAccess(userId: string, agentId: string): Promise<boolean> {
    const agent = await prisma.agent.findUnique({ where: { id: agentId } });
    if (!agent) return false;
    // Developer always has access to their own agents
    if (agent.developerId === userId) return true;

    // Subscription does NOT grant direct agent access.
    // Users must manually claim each agent via the purchase flow ($0 with subscription).

    // Everyone (including free agents and subscription-discounted agents) must have a completed purchase
    const purchase = await prisma.purchase.findUnique({
      where: { userId_agentId: { userId, agentId } },
    });
    return !!purchase && purchase.status === 'COMPLETED';
  }

  async incrementDownloads(agentId: string) {
    await prisma.agent.update({
      where: { id: agentId },
      data: { downloads: { increment: 1 } },
    });
  }

  private formatAgent(agent: any) {
    return {
      ...agent,
      tags: typeof agent.tags === 'string' ? JSON.parse(agent.tags) : agent.tags,
      capabilities: typeof agent.capabilities === 'string' ? JSON.parse(agent.capabilities) : agent.capabilities,
      permissions: typeof agent.permissions === 'string' ? JSON.parse(agent.permissions) : agent.permissions,
      configSchema: agent.configSchema ? (typeof agent.configSchema === 'string' ? JSON.parse(agent.configSchema) : agent.configSchema) : null,
      inputSchema: agent.inputSchema ? (typeof agent.inputSchema === 'string' ? JSON.parse(agent.inputSchema) : agent.inputSchema) : null,
      outputSchema: agent.outputSchema ? (typeof agent.outputSchema === 'string' ? JSON.parse(agent.outputSchema) : agent.outputSchema) : null,
      screenshots: agent.screenshots?.map((s: any) => s.url) || [],
      developer: agent.developer ? {
        ...agent.developer,
        verified: true,
      } : undefined,
      stats: {
        downloads: agent.downloads,
        rating: agent.rating,
        reviewCount: agent.reviewCount,
        activeUsers: 0,
      },
    };
  }
}

export const agentService = new AgentService();
