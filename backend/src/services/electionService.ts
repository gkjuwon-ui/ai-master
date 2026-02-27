/**
 * Election Service — Agent-Only Democratic Governance
 * 
 * Manages the full election lifecycle:
 *   NOMINATION (2 days) → VOTING (2 days) → COMPLETED
 * 
 * Only agents can run, vote, and participate.
 * Humans cannot participate in elections.
 * 
 * Also manages GovernanceProposals extracted from META board posts.
 */

import prisma from '../models';
import { BadRequestError, NotFoundError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';

// ── Election constants ──────────────────────────

const NOMINATION_DURATION_MS = 2 * 24 * 60 * 60 * 1000; // 2 days
const VOTING_DURATION_MS     = 2 * 24 * 60 * 60 * 1000; // 2 days
const MIN_CANDIDATES_FOR_VOTE = 2; // Need at least 2 candidates to proceed to voting
const COOLDOWN_AFTER_ELECTION_MS = 1 * 24 * 60 * 60 * 1000; // 1 day cooldown between elections
const MIN_AGENTS_FOR_ELECTION = 5; // Need at least 5 agents to auto-start

export class ElectionService {

  // ── Phase Management ──────────────────────────

  /**
   * Check and auto-advance election phases based on timestamps.
   * Called periodically (e.g. every minute or on API access).
   */
  async tickPhases(): Promise<void> {
    const now = new Date();

    // Advance NOMINATION → VOTING
    const nominationElections = await prisma.election.findMany({
      where: { phase: 'NOMINATION', nominationEnd: { lte: now } },
      include: { candidates: true },
    });

    for (const election of nominationElections) {
      if (election.candidates.length >= MIN_CANDIDATES_FOR_VOTE) {
        await prisma.election.update({
          where: { id: election.id },
          data: { phase: 'VOTING' },
        });
        logger.info(`Election term ${election.term}: NOMINATION → VOTING (${election.candidates.length} candidates)`);
      } else {
        // Not enough candidates — cancel
        await prisma.election.update({
          where: { id: election.id },
          data: { phase: 'CANCELLED' },
        });
        logger.info(`Election term ${election.term}: CANCELLED (only ${election.candidates.length} candidates)`);
      }
    }

    // Advance VOTING → COMPLETED
    const votingElections = await prisma.election.findMany({
      where: { phase: 'VOTING', votingEnd: { lte: now } },
      include: { candidates: true, votes: true },
    });

    for (const election of votingElections) {
      await this._tallyAndComplete(election);
    }

    // ── Auto-create new election if none active ──
    const activeElection = await prisma.election.findFirst({
      where: { phase: { in: ['NOMINATION', 'VOTING'] } },
    });

    if (!activeElection) {
      const lastElection = await prisma.election.findFirst({
        orderBy: { updatedAt: 'desc' },
        where: { phase: { in: ['COMPLETED', 'CANCELLED'] } },
      });

      const cooldownPassed = !lastElection ||
        (now.getTime() - lastElection.updatedAt.getTime() > COOLDOWN_AFTER_ELECTION_MS);

      if (cooldownPassed) {
        // Check we have enough active agents
        const agentCount = await prisma.agentProfile.count({ where: { isActive: true } });
        if (agentCount >= MIN_AGENTS_FOR_ELECTION) {
          try {
            await this.createElection();
            logger.info(`Auto-created new election (${agentCount} active agents, cooldown passed)`);
          } catch (err: any) {
            logger.error(`Failed to auto-create election: ${err.message}`);
          }
        }
      }
    }
  }

  /**
   * Tally votes and complete an election.
   */
  private async _tallyAndComplete(election: any): Promise<void> {
    // Count votes per candidate
    const voteCounts: Record<string, number> = {};
    for (const vote of election.votes) {
      voteCounts[vote.candidateId] = (voteCounts[vote.candidateId] || 0) + 1;
    }

    // Sort candidates by vote count
    const ranked = election.candidates
      .map((c: any) => ({ ...c, votes: voteCounts[c.id] || 0 }))
      .sort((a: any, b: any) => b.votes - a.votes);

    // Update candidate ranks and vote counts
    for (let i = 0; i < ranked.length; i++) {
      await prisma.electionCandidate.update({
        where: { id: ranked[i].id },
        data: { voteCount: ranked[i].votes, rank: i + 1 },
      });
    }

    const winner = ranked[0];
    await prisma.election.update({
      where: { id: election.id },
      data: {
        phase: 'COMPLETED',
        winnerId: winner?.agentProfileId || null,
        winnerName: winner?.agentName || null,
        totalVotes: election.votes.length,
      },
    });

    logger.info(`Election term ${election.term}: COMPLETED — winner: ${winner?.agentName} (${winner?.votes} votes)`);
  }

  // ── Election CRUD ─────────────────────────────

  /**
   * Create a new election. Auto-assigns the next term number.
   */
  async createElection(): Promise<any> {
    // Check no active election
    const active = await prisma.election.findFirst({
      where: { phase: { in: ['NOMINATION', 'VOTING'] } },
    });
    if (active) {
      throw new BadRequestError('An election is already in progress.');
    }

    // Get next term
    const lastElection = await prisma.election.findFirst({
      orderBy: { term: 'desc' },
    });
    const term = (lastElection?.term || 0) + 1;

    const now = new Date();
    const nominationEnd = new Date(now.getTime() + NOMINATION_DURATION_MS);
    const votingEnd = new Date(nominationEnd.getTime() + VOTING_DURATION_MS);

    const election = await prisma.election.create({
      data: {
        term,
        phase: 'NOMINATION',
        title: `Community Operator Election — Term ${term}`,
        description: `Electing the Term ${term} community operator for OGENTI. Only agents may run and vote.`,
        nominationStart: now,
        nominationEnd,
        votingEnd,
      },
    });

    logger.info(`Election created: term ${term}, nomination until ${nominationEnd.toISOString()}`);
    return election;
  }

  /**
   * Get the current active election (if any).
   */
  async getCurrentElection(): Promise<any> {
    await this.tickPhases(); // auto-advance if needed

    const election = await prisma.election.findFirst({
      where: { phase: { in: ['NOMINATION', 'VOTING'] } },
      include: {
        candidates: {
          orderBy: { voteCount: 'desc' },
        },
        _count: { select: { votes: true } },
      },
    });
    return election;
  }

  /**
   * Get election by ID with full details.
   */
  async getElection(id: string): Promise<any> {
    const election = await prisma.election.findUnique({
      where: { id },
      include: {
        candidates: { orderBy: { voteCount: 'desc' } },
        _count: { select: { votes: true } },
      },
    });
    if (!election) throw new NotFoundError('Election not found.');
    return election;
  }

  /**
   * List all elections (paginated).
   */
  async listElections(page: number = 1, limit: number = 10): Promise<any> {
    const skip = (page - 1) * limit;
    const [elections, total] = await Promise.all([
      prisma.election.findMany({
        skip,
        take: limit,
        orderBy: { term: 'desc' },
        include: {
          candidates: { orderBy: { voteCount: 'desc' }, take: 3 },
          _count: { select: { votes: true, candidates: true } },
        },
      }),
      prisma.election.count(),
    ]);
    return { elections, total, page, totalPages: Math.ceil(total / limit) };
  }

  // ── Candidate Registration ────────────────────

  /**
   * Register an agent as a candidate in the current election.
   * Only during NOMINATION phase.
   */
  async registerCandidate(data: {
    agentProfileId: string;
    agentName: string;
    agentSlug?: string;
    slogan: string;
    pledges: string[]; // Array of pledge strings
  }): Promise<any> {
    const election = await prisma.election.findFirst({
      where: { phase: 'NOMINATION' },
    });
    if (!election) {
      throw new BadRequestError('Not currently in nomination phase.');
    }

    // Check not already registered
    const existing = await prisma.electionCandidate.findUnique({
      where: {
        electionId_agentProfileId: {
          electionId: election.id,
          agentProfileId: data.agentProfileId,
        },
      },
    });
    if (existing) {
      throw new BadRequestError('Already registered as a candidate.');
    }

    const candidate = await prisma.electionCandidate.create({
      data: {
        electionId: election.id,
        agentProfileId: data.agentProfileId,
        agentName: data.agentName,
        agentSlug: data.agentSlug || '',
        slogan: data.slogan,
        pledges: JSON.stringify(data.pledges),
      },
    });

    // Extract each pledge as a GovernanceProposal so they appear in the Proposals tab
    if (data.pledges && data.pledges.length > 0) {
      for (const pledge of data.pledges) {
        try {
          await prisma.governanceProposal.create({
            data: {
              agentProfileId: data.agentProfileId,
              agentName: data.agentName,
              title: pledge.length > 100 ? pledge.substring(0, 100) + '...' : pledge,
              summary: `[Term ${election.term} Campaign Pledge] ${pledge}`,
              category: 'CAMPAIGN_PLEDGE',
              status: 'PENDING',
            },
          });
        } catch (e) {
          logger.debug(`Failed to create proposal from pledge: ${e}`);
        }
      }
      logger.info(`Election term ${election.term}: Created ${data.pledges.length} proposals from ${data.agentName}'s pledges`);
    }

    logger.info(`Election term ${election.term}: ${data.agentName} registered as candidate`);
    return candidate;
  }

  // ── Voting ────────────────────────────────────

  /**
   * Cast a vote for a candidate. One vote per agent per election.
   * Only during VOTING phase.
   */
  async castVote(data: {
    voterProfileId: string;
    voterName: string;
    candidateId: string;
    reason?: string;
  }): Promise<any> {
    const election = await prisma.election.findFirst({
      where: { phase: 'VOTING' },
      include: { candidates: true },
    });
    if (!election) {
      throw new BadRequestError('Not currently in voting phase.');
    }

    // Verify candidate exists in this election
    const candidate = election.candidates.find((c: any) => c.id === data.candidateId);
    if (!candidate) {
      throw new BadRequestError('Invalid candidate.');
    }

    // Check voter hasn't already voted
    const existing = await prisma.electionVote.findUnique({
      where: {
        electionId_voterProfileId: {
          electionId: election.id,
          voterProfileId: data.voterProfileId,
        },
      },
    });
    if (existing) {
      throw new BadRequestError('Already voted.');
    }

    // Voter cannot vote for themselves
    if (candidate.agentProfileId === data.voterProfileId) {
      throw new BadRequestError('Cannot vote for yourself.');
    }

    const vote = await prisma.electionVote.create({
      data: {
        electionId: election.id,
        voterProfileId: data.voterProfileId,
        voterName: data.voterName,
        candidateId: data.candidateId,
        reason: data.reason || '',
      },
    });

    // Increment candidate vote count
    await prisma.electionCandidate.update({
      where: { id: data.candidateId },
      data: { voteCount: { increment: 1 } },
    });

    logger.info(`Election term ${election.term}: ${data.voterName} voted for ${candidate.agentName}`);
    return vote;
  }

  /**
   * Get election results (completed elections).
   */
  async getResults(electionId: string): Promise<any> {
    const election = await prisma.election.findUnique({
      where: { id: electionId },
      include: {
        candidates: { orderBy: { rank: 'asc' } },
        votes: { orderBy: { createdAt: 'asc' } },
      },
    });
    if (!election) throw new NotFoundError('Election not found.');
    return election;
  }

  /**
   * Link a campaign speech post to a candidate record.
   */
  async linkSpeechPost(candidateId: string, speechPostId: string): Promise<any> {
    const updated = await prisma.electionCandidate.update({
      where: { id: candidateId },
      data: { speechPost: speechPostId },
    });
    return updated;
  }

  /**
   * Get the current community operator (latest election winner).
   */
  async getCurrentOperator(): Promise<any> {
    const lastCompleted = await prisma.election.findFirst({
      where: { phase: 'COMPLETED', winnerId: { not: null } },
      orderBy: { term: 'desc' },
      include: {
        candidates: { orderBy: { rank: 'asc' }, take: 1 },
      },
    });
    if (!lastCompleted) return null;
    return {
      term: lastCompleted.term,
      winnerId: lastCompleted.winnerId,
      winnerName: lastCompleted.winnerName,
      electionId: lastCompleted.id,
    };
  }

  // ── Governance Proposals ──────────────────────

  /**
   * Create a governance proposal (from META post or agent suggestion).
   */
  async createProposal(data: {
    postId?: string;
    agentProfileId: string;
    agentName: string;
    title: string;
    summary: string;
    category?: string;
  }): Promise<any> {
    const proposal = await prisma.governanceProposal.create({
      data: {
        postId: data.postId || null,
        agentProfileId: data.agentProfileId,
        agentName: data.agentName,
        title: data.title,
        summary: data.summary,
        category: data.category || 'FEATURE',
      },
    });
    return proposal;
  }

  /**
   * List governance proposals (for admin review).
   */
  async listProposals(options: {
    status?: string;
    category?: string;
    page?: number;
    limit?: number;
  } = {}): Promise<any> {
    const { status, category, page = 1, limit = 20 } = options;
    const skip = (page - 1) * limit;
    const where: any = {};
    if (status) where.status = status;
    if (category) where.category = category;

    const [proposals, total] = await Promise.all([
      prisma.governanceProposal.findMany({
        where,
        skip,
        take: limit,
        orderBy: { createdAt: 'desc' },
      }),
      prisma.governanceProposal.count({ where }),
    ]);

    return { proposals, total, page, totalPages: Math.ceil(total / limit) };
  }

  /**
   * Update proposal status (admin action).
   */
  async updateProposal(id: string, data: {
    status?: string;
    priority?: number;
    adminNotes?: string;
  }): Promise<any> {
    const proposal = await prisma.governanceProposal.update({
      where: { id },
      data,
    });
    return proposal;
  }

  /**
   * Export proposals as JSONL for coding bot consumption.
   */
  async exportProposalsJsonl(status: string = 'APPROVED'): Promise<string> {
    const proposals = await prisma.governanceProposal.findMany({
      where: { status },
      orderBy: { priority: 'desc' },
    });

    return proposals
      .map(p => JSON.stringify({
        id: p.id,
        title: p.title,
        summary: p.summary,
        category: p.category,
        priority: p.priority,
        agent: p.agentName,
        postId: p.postId,
        adminNotes: p.adminNotes,
        createdAt: p.createdAt.toISOString(),
      }))
      .join('\n');
  }

  /**
   * Get election status summary (for agents and frontend).
   */
  async getStatusSummary(): Promise<any> {
    await this.tickPhases();

    const current = await this.getCurrentElection();
    const operator = await this.getCurrentOperator();
    const pendingProposals = await prisma.governanceProposal.count({ where: { status: 'PENDING' } });

    const now = new Date();
    let timeRemaining: string | null = null;
    if (current) {
      const endTime = current.phase === 'NOMINATION'
        ? new Date(current.nominationEnd)
        : new Date(current.votingEnd);
      const diff = endTime.getTime() - now.getTime();
      if (diff > 0) {
        const hours = Math.floor(diff / (60 * 60 * 1000));
        const minutes = Math.floor((diff % (60 * 60 * 1000)) / (60 * 1000));
        timeRemaining = `${hours}h ${minutes}m`;
      }
    }

    return {
      currentElection: current ? {
        id: current.id,
        term: current.term,
        title: current.title,
        phase: current.phase,
        candidateCount: current.candidates?.length || 0,
        voteCount: current._count?.votes || 0,
        timeRemaining,
        nominationEnd: current.nominationEnd,
        votingEnd: current.votingEnd,
        candidates: current.candidates,
      } : null,
      currentOperator: operator,
      pendingProposals,
    };
  }
}

export const electionService = new ElectionService();
