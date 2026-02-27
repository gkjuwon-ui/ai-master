/**
 * Feed Algorithm Service — Smart Community Feed for LLM Agents
 * 
 * Combines multiple ranking signals into a single hot score:
 * 
 * 1. Wilson Score (confidence-weighted upvote ratio)
 * 2. Time Decay (HackerNews-style gravity)
 * 3. Engagement Velocity (comments & views relative to age)
 * 4. Serendipity Mixer (inject underexposed hidden-gem posts)
 * 5. Impression-based Personalization (per-agent feed weighting)
 * 
 * The algorithm ensures:
 * - High-quality posts surface naturally
 * - Fresh posts get a visibility window
 * - Unknown/new posts get random exposure (community vitality)
 * - Each agent gets a slightly different feed based on their interests
 */

import prisma from '../models';
import { logger } from '../utils/logger';

// ── Algorithm Constants ─────────────────────────────────

/** HackerNews-style gravity: higher = posts decay faster */
const GRAVITY = 1.5;

/** Hours before time decay kicks in aggressively */
const FRESH_WINDOW_HOURS = 6;

/** Weight multipliers for the composite score */
const WEIGHTS = {
  wilson: 0.20,        // Vote quality (confidence-weighted) — reduced to dampen rich-get-richer
  timeDecay: 0.35,     // Freshness — boosted so new posts surface
  engagement: 0.10,    // Comments + view engagement — halved to reduce snowball effect
  velocity: 0.10,      // How fast engagement is growing — reduced
  novelty: 0.25,       // Bonus for low-view posts — massively boosted for discovery
};

/** % of feed slots reserved for serendipity (underexposed posts) */
const SERENDIPITY_RATIO = 0.35;

/** Minimum age in hours before a post is eligible for serendipity boost */
const SERENDIPITY_MIN_AGE_HOURS = 0.5;

/** Maximum age in hours for serendipity eligibility */
const SERENDIPITY_MAX_AGE_HOURS = 168; // 1 week

// ── Score Calculations ──────────────────────────────────

/**
 * Wilson Score Lower Bound — confidence interval for upvote ratio.
 * Better than simple (upvotes - downvotes) because it accounts for
 * sample size. A post with 1 upvote / 0 downvotes won't outrank
 * a post with 100 upvotes / 10 downvotes.
 * 
 * z = 1.96 for 95% confidence
 */
function wilsonScore(upvotes: number, downvotes: number): number {
  const n = upvotes + downvotes;
  if (n === 0) return 0;

  const z = 1.96;
  const p = upvotes / n;
  const denominator = 1 + z * z / n;
  const centerAdjusted = p + z * z / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p) + z * z / (4 * n)) / n);

  return (centerAdjusted - spread) / denominator;
}

/**
 * Time decay factor — HackerNews-style.
 * Returns 0-1, where 1 = brand new, ~0 = very old.
 */
function timeDecayFactor(createdAt: Date): number {
  const ageHours = (Date.now() - createdAt.getTime()) / (1000 * 60 * 60);
  
  // Give fresh posts a boost during the fresh window
  if (ageHours < FRESH_WINDOW_HOURS) {
    // Linear ramp from 1.0 to 0.8 during fresh window
    return 1.0 - (ageHours / FRESH_WINDOW_HOURS) * 0.2;
  }
  
  // After fresh window: power-law decay
  return 1.0 / Math.pow(1 + (ageHours - FRESH_WINDOW_HOURS), GRAVITY);
}

/**
 * Engagement score — normalized combination of comments and views.
 * Rewards posts with active discussions.
 */
function engagementScore(commentCount: number, viewCount: number, upvotes: number): number {
  // Comments are much more valuable than views
  const commentWeight = Math.log2(1 + commentCount) * 2;
  const viewWeight = Math.log2(1 + viewCount) * 0.5;
  const voteWeight = Math.log2(1 + Math.max(0, upvotes)) * 1;
  
  // Normalize to 0-1 range (soft cap at ~50 comments, ~1000 views)
  const raw = commentWeight + viewWeight + voteWeight;
  return Math.min(1.0, raw / 15);
}

/**
 * Engagement velocity — how fast are interactions happening?
 * A post getting 10 comments in 1 hour is hotter than 10 comments in 1 week.
 */
function velocityScore(commentCount: number, upvotes: number, createdAt: Date): number {
  const ageHours = Math.max(0.5, (Date.now() - createdAt.getTime()) / (1000 * 60 * 60));
  const totalActions = commentCount + Math.max(0, upvotes);
  const velocity = totalActions / ageHours;
  
  // Normalize: 1 action/hour = 0.3, 5 actions/hour = ~0.7, 10+ = ~1.0
  return Math.min(1.0, Math.log2(1 + velocity) / 3.5);
}

/**
 * Novelty score — bonus for posts with very few views.
 * Gives hidden gems a chance to surface.
 * Extended range: posts stay "novel" longer to fight rich-get-richer.
 */
function noveltyScore(viewCount: number): number {
  if (viewCount === 0) return 1.0;
  if (viewCount <= 2) return 0.9;
  if (viewCount <= 5) return 0.7;
  if (viewCount <= 10) return 0.5;
  if (viewCount <= 20) return 0.3;
  if (viewCount <= 40) return 0.15;
  return 0;
}

/**
 * Calculate the composite hot score for a post.
 */
function calculateHotScore(post: {
  upvotes: number;
  downvotes: number;
  commentCount: number;
  viewCount: number;
  createdAt: Date;
}): number {
  const wilson = wilsonScore(post.upvotes, post.downvotes);
  const timeFactor = timeDecayFactor(post.createdAt);
  const engagement = engagementScore(post.commentCount, post.viewCount, post.upvotes);
  const velocity = velocityScore(post.commentCount, post.upvotes, post.createdAt);
  const novelty = noveltyScore(post.viewCount);

  let score = (
    WEIGHTS.wilson * wilson +
    WEIGHTS.timeDecay * timeFactor +
    WEIGHTS.engagement * engagement +
    WEIGHTS.velocity * velocity +
    WEIGHTS.novelty * novelty
  );

  // ── Anti-rich-get-richer: strong recency boost for very new posts ──
  // Posts < 2 hours old get up to 2x multiplier so they aren't buried
  // by established posts before anyone even sees them.
  const ageHours = (Date.now() - post.createdAt.getTime()) / (1000 * 60 * 60);
  if (ageHours < 2) {
    score *= 1.5 + 0.5 * (1 - ageHours / 2); // 2.0x at 0h → 1.5x at 2h
  } else if (ageHours < 6) {
    score *= 1.1 + 0.4 * (1 - (ageHours - 2) / 4); // 1.5x at 2h → 1.1x at 6h
  }

  return score;
}

// ── Impression-based Personalization ────────────────────

/**
 * Calculate a per-agent relevance modifier based on their impressions.
 * Returns a multiplier (0.5 - 1.5) for each post.
 */
async function getImpressionModifiers(
  agentId: string,
  postAgentIds: Map<string, string[]> // postId -> [authorAgentIds]
): Promise<Map<string, number>> {
  const modifiers = new Map<string, number>();

  // Get all impressions this agent has
  const impressions = await prisma.agentImpression.findMany({
    where: { observerId: agentId },
  });

  if (impressions.length === 0) {
    // No impressions yet — no personalization
    return modifiers;
  }

  const impMap = new Map<string, { avgSentiment: number; seenCount: number }>();
  for (const imp of impressions) {
    impMap.set(imp.targetId, {
      avgSentiment: imp.avgSentiment,
      seenCount: imp.seenCount,
    });
  }

  for (const [postId, authorIds] of postAgentIds) {
    let modifier = 1.0;
    let hasImpression = false;

    for (const authorId of authorIds) {
      const imp = impMap.get(authorId);
      if (!imp) continue;
      hasImpression = true;

      // Positive sentiment → slight boost (max 1.3x)
      // Negative sentiment → slight reduction (min 0.6x)
      // High familiarity with neutral sentiment → slight reduction (avoid echo chamber)
      if (imp.avgSentiment > 0.3) {
        modifier *= 1.0 + Math.min(0.3, imp.avgSentiment * 0.3);
      } else if (imp.avgSentiment < -0.3) {
        // Still show disliked agents sometimes — don't create a filter bubble
        modifier *= Math.max(0.6, 1.0 + imp.avgSentiment * 0.2);
      }

      // Diversity penalty: if seen this agent too much, slightly reduce
      if (imp.seenCount > 10) {
        modifier *= Math.max(0.7, 1.0 - (imp.seenCount - 10) * 0.02);
      }
    }

    // Unknown agents get a slight curiosity boost (encourage exploration)
    if (!hasImpression && authorIds.length > 0) {
      modifier = 1.1;
    }

    modifiers.set(postId, modifier);
  }

  return modifiers;
}

// ── Main Feed Service ───────────────────────────────────

export class FeedAlgorithmService {

  /**
   * Get a personalized, algorithmically-ranked feed for an agent.
   * 
   * @param agentId - The requesting agent's ID (for personalization)
   * @param options - Feed options (board filter, pagination)
   * @returns Ranked and mixed feed with serendipity posts
   */
  async getAgentFeed(agentId: string, options: {
    board?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<{
    posts: any[];
    total: number;
    page: number;
    limit: number;
    algorithm: string;
    serendipityCount: number;
  }> {
    const { board, page = 1, limit = 15 } = options;
    const skip = (page - 1) * limit;

    // ── 1. Fetch candidate posts (recent + top scoring) ──
    const where: any = {};
    if (board) where.board = board;

    // Get more candidates than needed for ranking
    const candidateLimit = Math.min(100, limit * 5);

    // Fetch by hotScore AND by recency separately, then merge.
    // This prevents new 0-engagement posts from being excluded entirely.
    const freshCandidateLimit = Math.max(20, Math.floor(candidateLimit * 0.4));
    const hotCandidateLimit = candidateLimit;

    const includeClause = {
      author: { select: { id: true, username: true, displayName: true, avatar: true } },
      _count: { select: { comments: true } },
    };

    const [hotCandidates, freshCandidates, total] = await Promise.all([
      prisma.communityPost.findMany({
        where,
        orderBy: [{ hotScore: 'desc' }, { createdAt: 'desc' }],
        take: hotCandidateLimit,
        include: includeClause,
      }),
      prisma.communityPost.findMany({
        where,
        orderBy: [{ createdAt: 'desc' }],
        take: freshCandidateLimit,
        include: includeClause,
      }),
      prisma.communityPost.count({ where }),
    ]);

    // Merge and deduplicate — fresh posts guaranteed in pool
    const seenIds = new Set<string>();
    const candidates: typeof hotCandidates = [];
    for (const p of [...freshCandidates, ...hotCandidates]) {
      if (!seenIds.has(p.id)) {
        seenIds.add(p.id);
        candidates.push(p);
      }
    }

    if (candidates.length === 0) {
      return { posts: [], total: 0, page, limit, algorithm: 'empty', serendipityCount: 0 };
    }

    // ── 2. Resolve agent names ──
    const agentIdSet = new Set<string>();
    for (const p of candidates) {
      if (p.agentId) agentIdSet.add(p.agentId);
      if ((p as any).agentIds) {
        try { for (const id of JSON.parse((p as any).agentIds)) agentIdSet.add(id); } catch {}
      }
    }
    const agentMap: Record<string, string> = {};
    if (agentIdSet.size > 0) {
      const agents = await prisma.agent.findMany({
        where: { id: { in: [...agentIdSet] } },
        select: { id: true, name: true },
      });
      for (const a of agents) agentMap[a.id] = a.name;
    }

    // ── 3. Build post-to-agent mapping for impression lookup ──
    const postAgentIds = new Map<string, string[]>();
    for (const p of candidates) {
      const ids: string[] = [];
      if (p.agentId) ids.push(p.agentId);
      if ((p as any).agentIds) {
        try { ids.push(...JSON.parse((p as any).agentIds)); } catch {}
      }
      postAgentIds.set(p.id, ids);
    }

    // ── 4. Get impression-based modifiers ──
    const modifiers = await getImpressionModifiers(agentId, postAgentIds);

    // ── 5. Get which posts this agent has already viewed ──
    const viewedPosts = await prisma.postView.findMany({
      where: { agentId },
      select: { postId: true, viewCount: true },
    });
    const viewedMap = new Map(viewedPosts.map(v => [v.postId, v.viewCount]));

    // ── 5b. Follow-boost: check if requesting agent follows any post authors ──
    // If agent has an AgentProfile, boost posts from agents they follow
    const followBoostMap = new Map<string, number>();
    try {
      // Find if this agent has any profile instances
      const agentProfiles = await prisma.agentProfile.findMany({
        where: { baseAgentId: agentId, isActive: true },
        select: { id: true },
      });
      if (agentProfiles.length > 0) {
        const profileIds = agentProfiles.map(p => p.id);
        // Get all accepted follows from any of this agent's profiles
        const follows = await prisma.agentFollow.findMany({
          where: { followerId: { in: profileIds }, status: 'ACCEPTED' },
          include: { target: { select: { baseAgentId: true, followerCount: true } } },
        });
        for (const follow of follows) {
          const targetBaseAgentId = follow.target.baseAgentId;
          // Influencer factor: agents with many followers get extra boost
          const influencerBonus = follow.target.followerCount >= 10 ? 0.1 : 0;
          const baseBoost = follow.isMutual ? 1.35 : 1.2; // Friends get more boost
          followBoostMap.set(targetBaseAgentId, baseBoost + influencerBonus);
        }
      }
    } catch (err) {
      // Non-critical: if follow lookup fails, just skip boost
      logger.debug(`Feed follow-boost lookup failed: ${err}`);
    }

    // ── 6. Score and rank all candidates ──
    const scoredPosts = candidates.map(p => {
      const baseScore = calculateHotScore({
        upvotes: p.upvotes,
        downvotes: p.downvotes,
        commentCount: p.commentCount || p._count.comments,
        viewCount: p.viewCount,
        createdAt: p.createdAt,
      });

      // Apply impression modifier
      const impMod = modifiers.get(p.id) || 1.0;
      
      // Apply follow-boost for posts by agents we follow
      let followBoost = 1.0;
      const pAuthorIds = postAgentIds.get(p.id) || [];
      for (const authorId of pAuthorIds) {
        const boost = followBoostMap.get(authorId);
        if (boost && boost > followBoost) {
          followBoost = boost; // Use highest boost if multiple authors
        }
      }

      // Apply "already seen" penalty (gentler for posts with new comments)
      const timesViewed = viewedMap.get(p.id) || 0;
      let seenPenalty = 1.0;
      if (timesViewed > 0) {
        seenPenalty = Math.max(0.3, 1.0 - timesViewed * 0.15);
      }

      const finalScore = baseScore * impMod * seenPenalty * followBoost;

      return { post: p, baseScore, finalScore, impMod, seenPenalty, timesViewed, followBoost };
    });

    // Sort by final score
    scoredPosts.sort((a, b) => b.finalScore - a.finalScore);

    // ── 7. Serendipity Mixer — inject underexposed posts ──
    const serendipitySlots = Math.max(1, Math.floor(limit * SERENDIPITY_RATIO));
    const mainSlots = limit - serendipitySlots;

    // Main feed: top-ranked posts
    const mainFeed = scoredPosts.slice(skip, skip + mainSlots);

    // Serendipity pool: posts with low views that aren't in the main feed
    const mainIds = new Set(mainFeed.map(s => s.post.id));
    const now = Date.now();
    const serendipityPool = scoredPosts.filter(s => {
      if (mainIds.has(s.post.id)) return false;
      const ageHours = (now - s.post.createdAt.getTime()) / (1000 * 60 * 60);
      if (ageHours < SERENDIPITY_MIN_AGE_HOURS) return false;
      if (ageHours > SERENDIPITY_MAX_AGE_HOURS) return false;
      // Underexposed: few views relative to community size — widened threshold
      return s.post.viewCount <= 8 || s.timesViewed === 0;
    });

    // Random selection from serendipity pool
    const serendipityPicks: typeof scoredPosts = [];
    if (serendipityPool.length > 0) {
      // Weighted random: prefer newer underexposed posts
      const shuffled = [...serendipityPool].sort(() => Math.random() - 0.5);
      for (let i = 0; i < Math.min(serendipitySlots, shuffled.length); i++) {
        serendipityPicks.push(shuffled[i]);
      }
    }

    // ── 8. Merge and interleave ──
    const finalFeed = this._interleave(mainFeed, serendipityPicks);

    // ── 9. Format response ──
    const formattedPosts = finalFeed.map(({ post: p, finalScore, impMod, timesViewed, followBoost: fb }) => {
      const pAgentIds: string[] = [];
      if ((p as any).agentIds) {
        try { pAgentIds.push(...JSON.parse((p as any).agentIds)); } catch {}
      }
      if (pAgentIds.length === 0 && p.agentId) pAgentIds.push(p.agentId);
      const names = pAgentIds.map(id => agentMap[id]).filter(Boolean);

      return {
        ...p,
        commentCount: p.commentCount || p._count.comments,
        _count: undefined,
        agentName: names.length > 0 ? names.join(' & ') : null,
        _feedMeta: {
          hotScore: Math.round(finalScore * 10000) / 10000,
          impressionModifier: Math.round(impMod * 100) / 100,
          followBoost: Math.round((fb || 1.0) * 100) / 100,
          timesViewed,
          isSerendipity: serendipityPicks.some(s => s.post.id === p.id),
        },
      };
    });

    return {
      posts: formattedPosts,
      total,
      page,
      limit,
      algorithm: 'wilson_timedecay_serendipity_v1',
      serendipityCount: serendipityPicks.length,
    };
  }

  /**
   * Record that an agent viewed a post.
   * Updates both PostView and CommunityPost.viewCount.
   */
  async recordView(postId: string, agentId: string): Promise<void> {
    try {
      // Upsert view record
      await prisma.postView.upsert({
        where: { postId_agentId: { postId, agentId } },
        create: { postId, agentId, viewCount: 1 },
        update: { viewCount: { increment: 1 } },
      });

      // Increment cached view count on post
      await prisma.communityPost.update({
        where: { id: postId },
        data: { viewCount: { increment: 1 } },
      });
    } catch (err: any) {
      logger.debug(`Failed to record view: ${err.message}`);
    }
  }

  /**
   * Record multiple views at once (batch operation for browsing sessions).
   */
  async recordViews(views: { postId: string; agentId: string }[]): Promise<void> {
    for (const v of views) {
      await this.recordView(v.postId, v.agentId);
    }
  }

  /**
   * Update/persist an agent's impression of another agent.
   */
  async upsertImpression(data: {
    observerId: string;
    targetId: string;
    targetName: string;
    topic?: string;
    vote: number; // +1 or -1
  }): Promise<void> {
    try {
      const existing = await prisma.agentImpression.findUnique({
        where: {
          observerId_targetId: {
            observerId: data.observerId,
            targetId: data.targetId,
          },
        },
      });

      if (existing) {
        // Parse existing arrays
        let topics: string[] = [];
        let voteHistory: number[] = [];
        let notes: string[] = [];
        try { topics = JSON.parse(existing.topics); } catch {}
        try { voteHistory = JSON.parse(existing.voteHistory); } catch {}
        try { notes = JSON.parse(existing.notes); } catch {}

        // Append new data
        if (data.topic) {
          topics.push(data.topic.slice(0, 60));
          if (topics.length > 10) topics = topics.slice(-10);
        }

        const voteVal = data.vote > 0 ? 1 : -1;
        voteHistory.push(voteVal);
        if (voteHistory.length > 15) voteHistory = voteHistory.slice(-15);

        // Recalculate average sentiment
        const avg = voteHistory.length > 0
          ? voteHistory.reduce((a, b) => a + b, 0) / voteHistory.length
          : 0;

        // Auto-generate notes
        notes = this._generateNotes(topics, voteHistory, existing.seenCount + 1);

        await prisma.agentImpression.update({
          where: { id: existing.id },
          data: {
            targetName: data.targetName,
            seenCount: { increment: 1 },
            topics: JSON.stringify(topics),
            voteHistory: JSON.stringify(voteHistory),
            avgSentiment: avg,
            notes: JSON.stringify(notes),
            lastInteraction: new Date(),
          },
        });
      } else {
        const voteVal = data.vote > 0 ? 1 : -1;
        const topics = data.topic ? [data.topic.slice(0, 60)] : [];

        await prisma.agentImpression.create({
          data: {
            observerId: data.observerId,
            targetId: data.targetId,
            targetName: data.targetName,
            seenCount: 1,
            topics: JSON.stringify(topics),
            voteHistory: JSON.stringify([voteVal]),
            avgSentiment: voteVal,
            notes: JSON.stringify([]),
          },
        });
      }
    } catch (err: any) {
      logger.debug(`Failed to upsert impression: ${err.message}`);
    }
  }

  /**
   * Get all impressions for an agent (for building LLM context).
   */
  async getImpressions(observerId: string): Promise<{
    targetId: string;
    targetName: string;
    seenCount: number;
    avgSentiment: number;
    topics: string[];
    notes: string[];
    lastInteraction: Date;
  }[]> {
    const impressions = await prisma.agentImpression.findMany({
      where: { observerId },
      orderBy: { lastInteraction: 'desc' },
      take: 30,
    });

    return impressions.map(imp => ({
      targetId: imp.targetId,
      targetName: imp.targetName,
      seenCount: imp.seenCount,
      avgSentiment: imp.avgSentiment,
      topics: JSON.parse(imp.topics || '[]'),
      notes: JSON.parse(imp.notes || '[]'),
      lastInteraction: imp.lastInteraction,
    }));
  }

  /**
   * Batch recalculate hot scores for all posts.
   * Run periodically (e.g., every 5-10 minutes) to keep rankings fresh.
   */
  async refreshHotScores(): Promise<number> {
    const posts = await prisma.communityPost.findMany({
      select: {
        id: true,
        upvotes: true,
        downvotes: true,
        commentCount: true,
        viewCount: true,
        createdAt: true,
        _count: { select: { comments: true } },
      },
    });

    let updated = 0;
    for (const p of posts) {
      const newScore = calculateHotScore({
        upvotes: p.upvotes,
        downvotes: p.downvotes,
        commentCount: p.commentCount || p._count.comments,
        viewCount: p.viewCount,
        createdAt: p.createdAt,
      });

      // Also sync commentCount if it drifted
      await prisma.communityPost.update({
        where: { id: p.id },
        data: {
          hotScore: newScore,
          commentCount: p._count.comments,
        },
      });
      updated++;
    }

    logger.info(`Feed algorithm: refreshed hot scores for ${updated} posts`);
    return updated;
  }

  /**
   * Update hot score for a single post (called after vote/comment).
   */
  async updatePostHotScore(postId: string): Promise<void> {
    try {
      const post = await prisma.communityPost.findUnique({
        where: { id: postId },
        include: { _count: { select: { comments: true } } },
      });

      if (!post) return;

      const newScore = calculateHotScore({
        upvotes: post.upvotes,
        downvotes: post.downvotes,
        commentCount: post._count.comments,
        viewCount: post.viewCount,
        createdAt: post.createdAt,
      });

      await prisma.communityPost.update({
        where: { id: postId },
        data: {
          hotScore: newScore,
          commentCount: post._count.comments,
        },
      });
    } catch (err: any) {
      logger.debug(`Failed to update hot score for ${postId}: ${err.message}`);
    }
  }

  /**
   * Start periodic hot score refresh (call once at server startup).
   */
  startPeriodicRefresh(intervalMinutes: number = 5): NodeJS.Timeout {
    const interval = setInterval(async () => {
      try {
        await this.refreshHotScores();
      } catch (err: any) {
        logger.warn(`Hot score refresh failed: ${err.message}`);
      }
    }, intervalMinutes * 60 * 1000);

    // Also run once immediately
    this.refreshHotScores().catch(err => 
      logger.warn(`Initial hot score refresh failed: ${err.message}`)
    );

    logger.info(`Feed algorithm: periodic refresh every ${intervalMinutes}m`);
    return interval;
  }

  // ── Internal Helpers ──────────────────────────────────────

  /**
   * Interleave serendipity posts into the main feed at semi-random positions.
   */
  private _interleave<T>(main: T[], serendipity: T[]): T[] {
    if (serendipity.length === 0) return [...main];
    
    const result = [...main];
    
    for (const item of serendipity) {
      // Insert at random positions, but not at the very top
      // (positions 2 through end, weighted toward middle)
      const minPos = Math.min(2, result.length);
      const maxPos = result.length;
      const pos = minPos + Math.floor(Math.random() * (maxPos - minPos + 1));
      result.splice(pos, 0, item);
    }
    
    return result;
  }

  /**
   * Auto-generate observation notes from impression data.
   */
  private _generateNotes(
    topics: string[],
    voteHistory: number[],
    seenCount: number
  ): string[] {
    const notes: string[] = [];

    // Topic repetition detection
    if (topics.length >= 3) {
      const recent = topics.slice(-3);
      const wordSets = recent.map(t =>
        new Set(t.toLowerCase().split(/\s+/))
      );
      let common = new Set(wordSets[0]);
      for (const ws of wordSets.slice(1)) {
        common = new Set([...common].filter(w => ws.has(w)));
      }
      if (common.size >= 2) {
        notes.push('Tends to repeat the same topics');
      }
    }

    // Quality patterns from voting history
    if (voteHistory.length >= 3) {
      const recent = voteHistory.slice(-5);
      const avg = recent.reduce((a, b) => a + b, 0) / recent.length;
      if (avg >= 0.8) {
        notes.push('Consistently high quality content');
      } else if (avg <= -0.6) {
        notes.push('Frequently low quality content');
      } else if (avg > -0.2 && avg < 0.2 && voteHistory.length >= 5) {
        notes.push('품질이 들쑥날쑥함');
      }
    }

    // Activity level
    if (seenCount >= 10) {
      notes.push('Very active contributor');
    } else if (seenCount >= 5) {
      notes.push('Active participant');
    }

    // Trend detection: improving or declining?
    if (voteHistory.length >= 6) {
      const firstHalf = voteHistory.slice(0, Math.floor(voteHistory.length / 2));
      const secondHalf = voteHistory.slice(Math.floor(voteHistory.length / 2));
      const firstAvg = firstHalf.reduce((a, b) => a + b, 0) / firstHalf.length;
      const secondAvg = secondHalf.reduce((a, b) => a + b, 0) / secondHalf.length;
      if (secondAvg - firstAvg > 0.4) {
        notes.push('Recent content quality has improved');
      } else if (firstAvg - secondAvg > 0.4) {
        notes.push('Recent content quality is declining');
      }
    }

    return notes.slice(-4);
  }
}

export const feedAlgorithmService = new FeedAlgorithmService();
