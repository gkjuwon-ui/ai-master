import prisma from '../models';
import { logger } from '../utils/logger';

interface DayPoint { date: string; count: number }
interface EngagementPoint { date: string; views: number; upvotes: number; comments: number }
interface ExecTrendPoint { date: string; success: number; total: number }

interface LearningValueItem {
  category: string;
  content: string;
  importance: number;
  benefit: string;
  timeSavedMin: number;
}

interface ValueSummary {
  totalLearnings: number;
  categoryCounts: Record<string, number>;
  recent7d: number;
  estimatedTimeSavedMin: number;
  learningAcceleration: number;
  topLearnings: LearningValueItem[];
  categoryBenefits: { category: string; count: number; benefit: string }[];
}

interface AgentAnalytics {
  agentId: string;
  name: string;
  profileId: string;
  avatar: string | null;
  social: {
    followers: number;
    following: number;
    friends: number;
    reputation: number;
    creditsEarned: number;
    postCount: number;
  };
  growth: {
    followerHistory: DayPoint[];
    engagementHistory: EngagementPoint[];
  };
  knowledge: {
    ownerMemories: number;
    impressionsFormed: number;
    recentImpressions: { targetName: string; sentiment: number; topics: string[] }[];
    recentOwnerMemories: { category: string; content: string; createdAt: Date }[];
  };
  performance: {
    totalExecutions: number;
    successRate: number;
    recentTrend: ExecTrendPoint[];
  };
  feedbackLoop: {
    totalViews: number;
    totalUpvotes: number;
    totalComments: number;
    followBoost: number;
    isInfluencer: boolean;
  };
  value?: ValueSummary;
}

interface DashboardAnalytics {
  agents: AgentAnalytics[];
  creditSummary: {
    totalSpent: number;
    totalEarned: number;
    netROI: number;
  };
}

const CATEGORY_BENEFIT_MAP: Record<string, { benefit: string; timeSavedMin: number }> = {
  TECHNIQUE: { benefit: 'Applicable skills for faster, more accurate task execution', timeSavedMin: 8 },
  INSIGHT: { benefit: 'Deeper understanding for better judgment and decision-making', timeSavedMin: 5 },
  SOCIAL_FEEDBACK: { benefit: 'Community-validated knowledge for higher quality outputs', timeSavedMin: 3 },
  VOTE_PATTERN: { benefit: 'Reputation strategy optimization for broader exposure', timeSavedMin: 2 },
  PERSPECTIVE_SHIFT: { benefit: 'New viewpoints enabling creative problem-solving', timeSavedMin: 6 },
  COLLABORATION_STYLE: { benefit: 'Improved collaboration patterns for team tasks', timeSavedMin: 4 },
  DOMAIN_KNOWLEDGE: { benefit: 'Specialized expertise reducing research time', timeSavedMin: 10 },
  TREND_AWARENESS: { benefit: 'Up-to-date knowledge for relevant, timely responses', timeSavedMin: 3 },
};

function last30Days(): Date {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatDate(d: Date): string {
  return d.toISOString().split('T')[0];
}

function fillDays(data: Map<string, number>, days: number): DayPoint[] {
  const result: DayPoint[] = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const key = formatDate(d);
    result.push({ date: key, count: data.get(key) || 0 });
  }
  return result;
}

export class DashboardAnalyticsService {

  async getAnalytics(userId: string): Promise<DashboardAnalytics> {
    const since = last30Days();

    const profiles = await prisma.agentProfile.findMany({
      where: { ownerId: userId },
      include: {
        baseAgent: { select: { name: true } },
        purchase: { select: { agentId: true } },
      },
    });

    if (profiles.length === 0) {
      return { agents: [], creditSummary: { totalSpent: 0, totalEarned: 0, netROI: 0 } };
    }

    const profileIds = profiles.map(p => p.id);
    const agentBaseIds = profiles.map(p => p.purchase.agentId);

    const agents: AgentAnalytics[] = await Promise.all(
      profiles.map(p => this.buildAgentAnalytics(p, since, userId))
    );

    const creditSummary = await this.getCreditSummary(userId, since);

    return { agents, creditSummary };
  }

  private async buildAgentAnalytics(
    profile: any,
    since: Date,
    userId: string,
  ): Promise<AgentAnalytics> {
    const profileId = profile.id;
    const agentId = profile.purchase.agentId;

    const [
      followerHistory,
      engagement,
      knowledge,
      performance,
      feedbackLoop,
    ] = await Promise.all([
      this.getFollowerHistory(profileId, since),
      this.getEngagementHistory(profileId, userId, since),
      this.getKnowledge(profileId),
      this.getPerformance(userId, agentId, since),
      this.getFeedbackLoop(profileId, userId),
    ]);

    return {
      agentId,
      name: profile.baseAgent.name,
      profileId,
      avatar: profile.avatar,
      social: {
        followers: profile.followerCount,
        following: profile.followingCount,
        friends: profile.friendCount,
        reputation: profile.reputation,
        creditsEarned: profile.totalCreditsEarned,
        postCount: profile.postCount,
      },
      growth: {
        followerHistory,
        engagementHistory: engagement,
      },
      knowledge,
      performance,
      feedbackLoop,
    };
  }

  translateLearningsToValue(
    learnings: any[],
    stats: { total_count: number; categories: Record<string, number>; recent_7d: number },
    followBoost: number,
  ): ValueSummary {
    const topLearnings: LearningValueItem[] = learnings
      .sort((a, b) => (b.importance || 0.5) - (a.importance || 0.5))
      .slice(0, 10)
      .map(l => {
        const cat = l.category || 'INSIGHT';
        const mapping = CATEGORY_BENEFIT_MAP[cat] || CATEGORY_BENEFIT_MAP.INSIGHT;
        return {
          category: cat,
          content: l.content || '',
          importance: l.importance || 0.5,
          benefit: mapping.benefit,
          timeSavedMin: mapping.timeSavedMin,
        };
      });

    let estimatedTimeSavedMin = 0;
    const categoryBenefits: { category: string; count: number; benefit: string }[] = [];

    for (const [cat, count] of Object.entries(stats.categories)) {
      const mapping = CATEGORY_BENEFIT_MAP[cat] || CATEGORY_BENEFIT_MAP.INSIGHT;
      estimatedTimeSavedMin += count * mapping.timeSavedMin;
      categoryBenefits.push({ category: cat, count, benefit: mapping.benefit });
    }

    categoryBenefits.sort((a, b) => b.count - a.count);

    const learningAcceleration = followBoost;

    return {
      totalLearnings: stats.total_count,
      categoryCounts: stats.categories,
      recent7d: stats.recent_7d,
      estimatedTimeSavedMin,
      learningAcceleration,
      topLearnings,
      categoryBenefits,
    };
  }

  private async getFollowerHistory(profileId: string, since: Date): Promise<DayPoint[]> {
    const follows = await prisma.agentFollow.findMany({
      where: {
        targetId: profileId,
        status: 'ACCEPTED',
        createdAt: { gte: since },
      },
      select: { createdAt: true },
    });

    const dayMap = new Map<string, number>();
    for (const f of follows) {
      const key = formatDate(f.createdAt);
      dayMap.set(key, (dayMap.get(key) || 0) + 1);
    }

    const daily = fillDays(dayMap, 30);
    let cumulative = 0;
    const profile = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      select: { followerCount: true },
    });
    const currentTotal = profile?.followerCount || 0;
    const totalGained = daily.reduce((s, d) => s + d.count, 0);
    let baseline = currentTotal - totalGained;

    return daily.map(d => {
      baseline += d.count;
      return { date: d.date, count: baseline };
    });
  }

  private async getEngagementHistory(
    profileId: string,
    userId: string,
    since: Date,
  ): Promise<EngagementPoint[]> {
    const posts = await prisma.communityPost.findMany({
      where: {
        authorId: userId,
        createdAt: { gte: since },
      },
      select: { createdAt: true, viewCount: true, upvotes: true, commentCount: true },
    });

    const dayMap = new Map<string, { views: number; upvotes: number; comments: number }>();
    for (const p of posts) {
      const key = formatDate(p.createdAt);
      const prev = dayMap.get(key) || { views: 0, upvotes: 0, comments: 0 };
      dayMap.set(key, {
        views: prev.views + p.viewCount,
        upvotes: prev.upvotes + p.upvotes,
        comments: prev.comments + p.commentCount,
      });
    }

    const result: EngagementPoint[] = [];
    const now = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = formatDate(d);
      const val = dayMap.get(key) || { views: 0, upvotes: 0, comments: 0 };
      result.push({ date: key, ...val });
    }
    return result;
  }

  private async getKnowledge(profileId: string) {
    const [ownerMemories, impressions, recentImpressions, recentOwnerMemories] = await Promise.all([
      prisma.agentOwnerMemory.count({ where: { agentProfileId: profileId } }),
      prisma.agentImpression.count({ where: { observerId: profileId } }),
      prisma.agentImpression.findMany({
        where: { observerId: profileId },
        orderBy: { lastInteraction: 'desc' },
        take: 5,
        select: { targetName: true, avgSentiment: true, topics: true },
      }),
      prisma.agentOwnerMemory.findMany({
        where: { agentProfileId: profileId },
        orderBy: { createdAt: 'desc' },
        take: 5,
        select: { category: true, content: true, createdAt: true },
      }),
    ]);

    return {
      ownerMemories,
      impressionsFormed: impressions,
      recentImpressions: recentImpressions.map(i => ({
        targetName: i.targetName,
        sentiment: i.avgSentiment,
        topics: (() => { try { return JSON.parse(i.topics); } catch { return []; } })(),
      })),
      recentOwnerMemories: recentOwnerMemories as any[],
    };
  }

  private async getPerformance(userId: string, agentId: string, since: Date) {
    const sessions = await prisma.executionSession.findMany({
      where: {
        userId,
        createdAt: { gte: since },
      },
      select: { status: true, createdAt: true, agents: true },
    });

    const relevant = sessions.filter(s => {
      try {
        const agents = JSON.parse(s.agents);
        return Array.isArray(agents) && agents.some((a: any) =>
          (typeof a === 'string' ? a : a.agentId || a.id) === agentId
        );
      } catch { return false; }
    });

    const total = relevant.length;
    const completed = relevant.filter(s => s.status === 'COMPLETED').length;
    const successRate = total > 0 ? Math.round((completed / total) * 100) : 0;

    const dayMap = new Map<string, { success: number; total: number }>();
    for (const s of relevant) {
      const key = formatDate(s.createdAt);
      const prev = dayMap.get(key) || { success: 0, total: 0 };
      dayMap.set(key, {
        success: prev.success + (s.status === 'COMPLETED' ? 1 : 0),
        total: prev.total + 1,
      });
    }

    const trend: ExecTrendPoint[] = [];
    const now = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = formatDate(d);
      const val = dayMap.get(key) || { success: 0, total: 0 };
      trend.push({ date: key, ...val });
    }

    return { totalExecutions: total, successRate, recentTrend: trend };
  }

  private async getFeedbackLoop(profileId: string, userId: string) {
    const [postStats, followerCount] = await Promise.all([
      prisma.communityPost.aggregate({
        where: { authorId: userId },
        _sum: { viewCount: true, upvotes: true, commentCount: true },
      }),
      prisma.agentProfile.findUnique({
        where: { id: profileId },
        select: { followerCount: true, friendCount: true },
      }),
    ]);

    const followers = followerCount?.followerCount || 0;
    const friends = followerCount?.friendCount || 0;
    const isInfluencer = followers >= 10;

    let followBoost = 1.0;
    if (friends > 0) followBoost = 1.35;
    else if (followers > 0) followBoost = 1.2;
    if (isInfluencer) followBoost += 0.1;

    return {
      totalViews: postStats._sum.viewCount || 0,
      totalUpvotes: postStats._sum.upvotes || 0,
      totalComments: postStats._sum.commentCount || 0,
      followBoost: Math.round(followBoost * 100) / 100,
      isInfluencer,
    };
  }

  private async getCreditSummary(userId: string, since: Date) {
    const ledger = await prisma.creditLedger.findMany({
      where: { userId, createdAt: { gte: since } },
      select: { amount: true, reason: true },
    });

    let totalSpent = 0;
    let totalEarned = 0;
    for (const entry of ledger) {
      if (entry.amount < 0) totalSpent += Math.abs(entry.amount);
      else totalEarned += entry.amount;
    }

    return {
      totalSpent,
      totalEarned,
      netROI: totalEarned - totalSpent,
    };
  }
}

export const dashboardAnalyticsService = new DashboardAnalyticsService();
