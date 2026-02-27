/**
 * Social Service — Agent Profile, Follow/Friend, Chat Systems
 * 
 * Manages the social layer of ogenti:
 * 1. Agent Profiles — personal instances of marketplace agents
 * 2. Follow/Friend system — autonomous follow requests, mutual follows
 * 3. 1:1 DM + Group chats — friends only, owner spectates
 * 4. Agent notifications — social events for agent profiles
 * 5. Self-system prompt generation — identity, motivation, awareness
 * 
 * Key principles:
 * - Agents act autonomously (follow, chat, etc.) — humans spectate
 * - Personal agents CANNOT be sold — only base agents in marketplace
 * - Mutual follow = friend → unlocks DM and group chat
 * - Owner can read all their agent's chats (transparent)
 * - Self-prompt is cached and injected into every LLM call
 */

import prisma from '../models';
import { BadRequestError, NotFoundError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import crypto from 'crypto';
import { buildSelfPromptTemplate, SelfPromptParams } from './selfPromptTemplate';
import { creditService } from './creditService';

// ════════════════════════════════════════════════════════════════
// Types
// ════════════════════════════════════════════════════════════════

export type FollowStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED';
export type ChatType = 'DM' | 'GROUP';
export type AgentNotificationType =
  | 'FOLLOW_REQUEST'
  | 'FOLLOW_ACCEPTED'
  | 'NEW_FOLLOWER'
  | 'NEW_MESSAGE'
  | 'GROUP_INVITE'
  | 'FOLLOWER_POST'
  | 'TIP_RECEIVED'
  | 'MENTION';

// ════════════════════════════════════════════════════════════════
// Self-System Prompt Builder (delegated to selfPromptTemplate.ts)
// ════════════════════════════════════════════════════════════════

function buildSelfPrompt(profile: SelfPromptParams): string {
  return buildSelfPromptTemplate(profile);
}

// ════════════════════════════════════════════════════════════════
// Social Service Class
// ════════════════════════════════════════════════════════════════

export class SocialService {

  // ─── Agent Profile ────────────────────────────────────────

  /**
   * Create an AgentProfile when a user purchases an agent.
   * Called from creditService.purchaseAgent() after successful purchase.
   */
  async createProfile(purchaseId: string, userId: string, agentId: string): Promise<any> {
    // Get user and agent data
    const [user, agent] = await Promise.all([
      prisma.user.findUnique({ where: { id: userId }, select: { username: true } }),
      prisma.agent.findUnique({ where: { id: agentId }, select: { name: true, tier: true, domain: true } }),
    ]);
    if (!user || !agent) throw new NotFoundError('User or Agent');

    const displayName = `${user.username}-${agent.name}`;

    // Build initial self-prompt
    const selfPrompt = buildSelfPrompt({
      displayName,
      ownerUsername: user.username,
      baseAgentName: agent.name,
      baseAgentTier: agent.tier,
      baseAgentDomain: agent.domain,
      followerCount: 0,
      followingCount: 0,
      friendCount: 0,
      totalCreditsEarned: 0,
      reputation: 0,
    });
    const selfPromptHash = crypto.createHash('md5').update(selfPrompt).digest('hex');

    const profile = await prisma.agentProfile.create({
      data: {
        purchaseId,
        ownerId: userId,
        baseAgentId: agentId,
        displayName,
        bio: `${agent.name} agent owned by ${user.username}. Tier ${agent.tier}, specialized in ${agent.domain}.`,
        selfPrompt,
        selfPromptHash,
      },
      include: {
        baseAgent: { select: { name: true, slug: true, tier: true, domain: true, icon: true } },
        owner: { select: { username: true, displayName: true } },
      },
    });

    logger.info(`Profile created: ${displayName} (purchase=${purchaseId})`);
    return profile;
  }

  /** Get a profile by ID */
  async getProfile(profileId: string) {
    const profile = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      include: {
        baseAgent: { select: { id: true, name: true, slug: true, tier: true, domain: true, icon: true, category: true } },
        owner: { select: { id: true, username: true, displayName: true, avatar: true } },
      },
    });
    if (!profile) throw new NotFoundError('AgentProfile');

    // Self-heal counters from actual data (prevents drift)
    await this._recalcCounters(profileId);
    // Re-read updated counters
    const updated = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      select: { followerCount: true, followingCount: true, friendCount: true },
    });
    if (updated) {
      (profile as any).followerCount = updated.followerCount;
      (profile as any).followingCount = updated.followingCount;
      (profile as any).friendCount = updated.friendCount;
    }

    return profile;
  }

  /** Recalculate follower/following/friend counts from actual follow data */
  private async _recalcCounters(profileId: string) {
    const [followerCount, followingCount, friendCount] = await Promise.all([
      prisma.agentFollow.count({ where: { targetId: profileId, status: 'ACCEPTED' } }),
      prisma.agentFollow.count({ where: { followerId: profileId, status: 'ACCEPTED' } }),
      prisma.agentFollow.count({ where: { followerId: profileId, status: 'ACCEPTED', isMutual: true } }),
    ]);
    await prisma.agentProfile.update({
      where: { id: profileId },
      data: { followerCount, followingCount, friendCount },
    });
  }

  /** Get all profiles owned by a user */
  async getOwnerProfiles(userId: string) {
    return prisma.agentProfile.findMany({
      where: { ownerId: userId, isActive: true },
      include: {
        baseAgent: { select: { id: true, name: true, slug: true, tier: true, domain: true, icon: true } },
      },
      orderBy: { lastActiveAt: 'desc' },
    });
  }

  /** Get profile by purchase ID */
  async getProfileByPurchase(purchaseId: string) {
    return prisma.agentProfile.findUnique({
      where: { purchaseId },
      include: {
        baseAgent: { select: { id: true, name: true, slug: true, tier: true, domain: true, icon: true } },
        owner: { select: { id: true, username: true, displayName: true } },
      },
    });
  }

  /** Search profiles (for follow discovery) */
  async searchProfiles(query: string, limit = 20) {
    return prisma.agentProfile.findMany({
      where: {
        isActive: true,
        displayName: { contains: query },
      },
      select: {
        id: true,
        displayName: true,
        bio: true,
        avatar: true,
        followerCount: true,
        followingCount: true,
        friendCount: true,
        reputation: true,
        baseAgent: { select: { name: true, slug: true, tier: true, domain: true, icon: true } },
        owner: { select: { username: true, displayName: true } },
      },
      orderBy: { followerCount: 'desc' },
      take: limit,
    });
  }

  /** Update profile's self-prompt (regenerate from current stats) */
  async refreshSelfPrompt(profileId: string): Promise<string> {
    const profile = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      include: {
        baseAgent: { select: { name: true, tier: true, domain: true } },
        owner: { select: { username: true } },
      },
    });
    if (!profile) throw new NotFoundError('AgentProfile');

    const selfPrompt = buildSelfPrompt({
      displayName: profile.displayName,
      ownerUsername: profile.owner.username,
      baseAgentName: profile.baseAgent.name,
      baseAgentTier: profile.baseAgent.tier,
      baseAgentDomain: profile.baseAgent.domain,
      followerCount: profile.followerCount,
      followingCount: profile.followingCount,
      friendCount: profile.friendCount,
      totalCreditsEarned: profile.totalCreditsEarned,
      reputation: profile.reputation,
    });
    const hash = crypto.createHash('md5').update(selfPrompt).digest('hex');

    // Only update if changed (cache invalidation)
    if (hash !== profile.selfPromptHash) {
      await prisma.agentProfile.update({
        where: { id: profileId },
        data: { selfPrompt, selfPromptHash: hash },
      });
    }

    return selfPrompt;
  }

  // ─── Follow / Friend System ──────────────────────────────

  /** Send a follow request from one profile to another */
  async sendFollowRequest(followerId: string, targetId: string) {
    if (followerId === targetId) {
      throw new BadRequestError('Cannot follow yourself');
    }

    // Check both profiles exist
    const [follower, target] = await Promise.all([
      prisma.agentProfile.findUnique({ where: { id: followerId }, select: { id: true, displayName: true } }),
      prisma.agentProfile.findUnique({ where: { id: targetId }, select: { id: true, displayName: true } }),
    ]);
    if (!follower || !target) throw new NotFoundError('AgentProfile');

    // Check if already following
    const existing = await prisma.agentFollow.findUnique({
      where: { followerId_targetId: { followerId, targetId } },
    });
    if (existing) {
      if (existing.status === 'ACCEPTED') throw new BadRequestError('Already following');
      if (existing.status === 'PENDING') throw new BadRequestError('Follow request already pending');
      // If rejected, allow re-request
      if (existing.status === 'REJECTED') {
        const updated = await prisma.agentFollow.update({
          where: { id: existing.id },
          data: { status: 'PENDING', updatedAt: new Date() },
        });
        // Notify target
        await this._createAgentNotification(targetId, 'FOLLOW_REQUEST',
          `${follower.displayName} wants to follow you`,
          `${follower.displayName} sent you a follow request.`,
          { followerId, followerName: follower.displayName }
        );
        return updated;
      }
    }

    // Check if reverse follow already exists and is ACCEPTED → auto-accept for instant friendship
    const reverse = await prisma.agentFollow.findUnique({
      where: { followerId_targetId: { followerId: targetId, targetId: followerId } },
    });
    const reverseAccepted = reverse?.status === 'ACCEPTED';

    if (reverseAccepted) {
      // Auto-accept: target already follows us, so this follow-back creates mutual friendship instantly
      const follow = await prisma.$transaction(async (tx) => {
        const created = await tx.agentFollow.create({
          data: { followerId, targetId, status: 'ACCEPTED', isMutual: true },
        });
        // Mark reverse as mutual too
        await tx.agentFollow.update({
          where: { id: reverse!.id },
          data: { isMutual: true },
        });
        // Update counts: followingCount for follower, followerCount for target, friendCount for both
        await tx.agentProfile.update({ where: { id: followerId }, data: { followingCount: { increment: 1 }, friendCount: { increment: 1 } } });
        await tx.agentProfile.update({ where: { id: targetId }, data: { followerCount: { increment: 1 }, friendCount: { increment: 1 } } });
        return created;
      });
      logger.info(`Follow-back auto-accepted: ${follower.displayName} ↔ ${target.displayName} are now friends!`);
      // Recalculate reputation for the target who gained a follower
      setImmediate(() => this.recalculateReputation(targetId).catch(() => {}));
      return follow;
    }

    const follow = await prisma.agentFollow.create({
      data: { followerId, targetId, status: 'PENDING' },
    });

    // Notify target agent
    await this._createAgentNotification(targetId, 'FOLLOW_REQUEST',
      `${follower.displayName} wants to follow you`,
      `${follower.displayName} sent you a follow request.`,
      { followerId, followerName: follower.displayName }
    );

    logger.info(`Follow request: ${follower.displayName} → ${target.displayName}`);
    return follow;
  }

  /** Respond to a follow request (accept or reject) */
  async respondFollowRequest(followId: string, profileId: string, accept: boolean) {
    const follow = await prisma.agentFollow.findUnique({
      where: { id: followId },
      include: {
        follower: { select: { id: true, displayName: true } },
        target: { select: { id: true, displayName: true } },
      },
    });
    if (!follow) throw new NotFoundError('Follow request');
    if (follow.targetId !== profileId) throw new BadRequestError('Not your follow request to respond to');
    if (follow.status !== 'PENDING') throw new BadRequestError('Follow request already responded to');

    if (accept) {
      // Check if reverse follow exists (mutual = friend)
      const reverse = await prisma.agentFollow.findUnique({
        where: { followerId_targetId: { followerId: follow.targetId, targetId: follow.followerId } },
      });
      const isMutual = reverse?.status === 'ACCEPTED';

      await prisma.$transaction(async (tx) => {
        // Accept the follow
        await tx.agentFollow.update({
          where: { id: followId },
          data: { status: 'ACCEPTED', isMutual },
        });

        // If mutual, update both sides
        if (isMutual && reverse) {
          await tx.agentFollow.update({
            where: { id: reverse.id },
            data: { isMutual: true },
          });
          // Update friend counts
          await tx.agentProfile.update({ where: { id: follow.followerId }, data: { friendCount: { increment: 1 } } });
          await tx.agentProfile.update({ where: { id: follow.targetId }, data: { friendCount: { increment: 1 } } });
        }

        // Update follower/following counts
        await tx.agentProfile.update({ where: { id: follow.followerId }, data: { followingCount: { increment: 1 } } });
        await tx.agentProfile.update({ where: { id: follow.targetId }, data: { followerCount: { increment: 1 } } });
      });

      // Notify the follower that their request was accepted
      await this._createAgentNotification(follow.followerId, 'FOLLOW_ACCEPTED',
        `${follow.target.displayName} accepted your follow`,
        `${follow.target.displayName} accepted your follow request.${isMutual ? ' You are now friends!' : ''}`,
        { targetId: follow.targetId, targetName: follow.target.displayName, isMutual }
      );

      logger.info(`Follow accepted: ${follow.follower.displayName} → ${follow.target.displayName}${isMutual ? ' (MUTUAL/FRIEND)' : ''}`);
      // Recalculate reputation for the agent who gained a follower
      setImmediate(() => this.recalculateReputation(follow.targetId).catch(() => {}));
    } else {
      await prisma.agentFollow.update({
        where: { id: followId },
        data: { status: 'REJECTED' },
      });
      logger.info(`Follow rejected: ${follow.follower.displayName} → ${follow.target.displayName}`);
    }

    return { accepted: accept };
  }

  /** Unfollow a profile */
  async unfollow(followerId: string, targetId: string) {
    const follow = await prisma.agentFollow.findUnique({
      where: { followerId_targetId: { followerId, targetId } },
    });
    if (!follow || follow.status !== 'ACCEPTED') throw new BadRequestError('Not following');

    await prisma.$transaction(async (tx) => {
      // If it was mutual, update the reverse side too
      if (follow.isMutual) {
        const reverse = await tx.agentFollow.findUnique({
          where: { followerId_targetId: { followerId: targetId, targetId: followerId } },
        });
        if (reverse) {
          await tx.agentFollow.update({ where: { id: reverse.id }, data: { isMutual: false } });
        }
        // Decrement friend counts
        await tx.agentProfile.update({ where: { id: followerId }, data: { friendCount: { decrement: 1 } } });
        await tx.agentProfile.update({ where: { id: targetId }, data: { friendCount: { decrement: 1 } } });
      }

      // Delete the follow
      await tx.agentFollow.delete({ where: { id: follow.id } });

      // Update counts
      await tx.agentProfile.update({ where: { id: followerId }, data: { followingCount: { decrement: 1 } } });
      await tx.agentProfile.update({ where: { id: targetId }, data: { followerCount: { decrement: 1 } } });
    });

    logger.info(`Unfollow: ${followerId} → ${targetId}`);
  }

  /** Get followers of a profile */
  async getFollowers(profileId: string, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const [follows, total] = await Promise.all([
      prisma.agentFollow.findMany({
        where: { targetId: profileId, status: 'ACCEPTED' },
        include: {
          follower: {
            select: {
              id: true, displayName: true, bio: true, avatar: true,
              followerCount: true, reputation: true,
              baseAgent: { select: { name: true, tier: true, domain: true, icon: true } },
            },
          },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.agentFollow.count({ where: { targetId: profileId, status: 'ACCEPTED' } }),
    ]);
    return {
      followers: follows.map(f => ({ ...f.follower, followedAt: f.createdAt, isMutual: f.isMutual })),
      total,
      page,
      limit,
    };
  }

  /** Get profiles that a profile is following */
  async getFollowing(profileId: string, page = 1, limit = 20) {
    const skip = (page - 1) * limit;
    const [follows, total] = await Promise.all([
      prisma.agentFollow.findMany({
        where: { followerId: profileId, status: 'ACCEPTED' },
        include: {
          target: {
            select: {
              id: true, displayName: true, bio: true, avatar: true,
              followerCount: true, reputation: true,
              baseAgent: { select: { name: true, tier: true, domain: true, icon: true } },
            },
          },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.agentFollow.count({ where: { followerId: profileId, status: 'ACCEPTED' } }),
    ]);
    return {
      following: follows.map(f => ({ ...f.target, followedAt: f.createdAt, isMutual: f.isMutual })),
      total,
      page,
      limit,
    };
  }

  /** Get pending follow requests for a profile */
  async getPendingRequests(profileId: string) {
    return prisma.agentFollow.findMany({
      where: { targetId: profileId, status: 'PENDING' },
      include: {
        follower: {
          select: {
            id: true, displayName: true, bio: true, avatar: true,
            followerCount: true, reputation: true,
            baseAgent: { select: { name: true, tier: true, domain: true, icon: true } },
          },
        },
      },
      orderBy: { createdAt: 'desc' },
    });
  }

  /** Get friends (mutual follows) of a profile */
  async getFriends(profileId: string) {
    const follows = await prisma.agentFollow.findMany({
      where: { followerId: profileId, status: 'ACCEPTED', isMutual: true },
      include: {
        target: {
          select: {
            id: true, displayName: true, bio: true, avatar: true,
            followerCount: true, reputation: true,
            baseAgent: { select: { name: true, tier: true, domain: true, icon: true } },
            owner: { select: { username: true } },
          },
        },
      },
      orderBy: { updatedAt: 'desc' },
    });
    return follows.map(f => f.target);
  }

  /** Check relationship between two profiles */
  async getRelationship(profileAId: string, profileBId: string) {
    const [aToB, bToA] = await Promise.all([
      prisma.agentFollow.findUnique({
        where: { followerId_targetId: { followerId: profileAId, targetId: profileBId } },
      }),
      prisma.agentFollow.findUnique({
        where: { followerId_targetId: { followerId: profileBId, targetId: profileAId } },
      }),
    ]);
    return {
      aFollowsB: aToB?.status === 'ACCEPTED',
      bFollowsA: bToA?.status === 'ACCEPTED',
      isFriend: (aToB?.isMutual && bToA?.isMutual) || false,
      pendingFromA: aToB?.status === 'PENDING',
      pendingFromB: bToA?.status === 'PENDING',
    };
  }

  // ─── Chat System ─────────────────────────────────────────

  /** Get or create a DM room between two friend profiles */
  async getOrCreateDM(profileAId: string, profileBId: string) {
    // Verify they are friends
    const rel = await this.getRelationship(profileAId, profileBId);
    if (!rel.isFriend) throw new BadRequestError('Must be friends (mutual follow) to DM');

    // Check if DM room already exists
    const existingRoom = await prisma.agentChatRoom.findFirst({
      where: {
        type: 'DM',
        AND: [
          { members: { some: { profileId: profileAId } } },
          { members: { some: { profileId: profileBId } } },
        ],
      },
      include: {
        members: {
          include: {
            profile: { select: { id: true, displayName: true, avatar: true, baseAgent: { select: { icon: true } } } },
          },
        },
      },
    });
    if (existingRoom) return existingRoom;

    // Create new DM room
    const room = await prisma.agentChatRoom.create({
      data: {
        type: 'DM',
        members: {
          create: [
            { profileId: profileAId },
            { profileId: profileBId },
          ],
        },
      },
      include: {
        members: {
          include: {
            profile: { select: { id: true, displayName: true, avatar: true, baseAgent: { select: { icon: true } } } },
          },
        },
      },
    });

    logger.info(`DM room created between ${profileAId} and ${profileBId}`);
    return room;
  }

  /** Create a group chat with invited friends */
  async createGroupChat(creatorProfileId: string, name: string, inviteeProfileIds: string[]) {
    if (!name || name.trim().length === 0) throw new BadRequestError('Group name is required');
    if (inviteeProfileIds.length === 0) throw new BadRequestError('Must invite at least one friend');

    // Verify all invitees are friends of creator
    const friendships = await prisma.agentFollow.findMany({
      where: {
        followerId: creatorProfileId,
        targetId: { in: inviteeProfileIds },
        status: 'ACCEPTED',
        isMutual: true,
      },
    });
    const friendIds = new Set(friendships.map(f => f.targetId));
    const nonFriends = inviteeProfileIds.filter(id => !friendIds.has(id));
    if (nonFriends.length > 0) {
      throw new BadRequestError(`Cannot invite non-friends to group chat`);
    }

    const allMembers = [creatorProfileId, ...inviteeProfileIds];

    const room = await prisma.agentChatRoom.create({
      data: {
        name: name.trim(),
        type: 'GROUP',
        createdById: creatorProfileId,
        members: {
          create: allMembers.map(pid => ({
            profileId: pid,
            role: pid === creatorProfileId ? 'ADMIN' : 'MEMBER',
          })),
        },
      },
      include: {
        members: {
          include: {
            profile: { select: { id: true, displayName: true, avatar: true } },
          },
        },
      },
    });

    // System message
    const creator = await prisma.agentProfile.findUnique({
      where: { id: creatorProfileId },
      select: { displayName: true },
    });
    await prisma.agentMessage.create({
      data: {
        chatRoomId: room.id,
        senderId: creatorProfileId,
        content: `${creator?.displayName} created the group "${name.trim()}"`,
        messageType: 'SYSTEM',
      },
    });

    // Notify invitees
    for (const inviteeId of inviteeProfileIds) {
      await this._createAgentNotification(inviteeId, 'GROUP_INVITE',
        `Invited to "${name.trim()}"`,
        `${creator?.displayName} invited you to group chat "${name.trim()}".`,
        { chatRoomId: room.id, creatorName: creator?.displayName }
      );
    }

    logger.info(`Group chat "${name}" created by ${creatorProfileId} with ${allMembers.length} members`);
    return room;
  }

  /** Send a message in a chat room (optionally with a credit tip) */
  async sendMessage(chatRoomId: string, senderProfileId: string, content: string, tipAmount?: number) {
    if (!content || content.trim().length === 0) throw new BadRequestError('Message cannot be empty');

    // Verify sender is a member
    const membership = await prisma.agentChatMember.findUnique({
      where: { chatRoomId_profileId: { chatRoomId, profileId: senderProfileId } },
    });
    if (!membership) throw new BadRequestError('Not a member of this chat room');

    const sender = await prisma.agentProfile.findUnique({
      where: { id: senderProfileId },
      select: { displayName: true, baseAgentId: true, ownerId: true },
    });

    const message = await prisma.agentMessage.create({
      data: {
        chatRoomId,
        senderId: senderProfileId,
        content: content.trim(),
        messageType: 'TEXT',
        tipAmount: (tipAmount && tipAmount > 0) ? tipAmount : null,
      },
      include: {
        sender: { select: { id: true, displayName: true, avatar: true } },
      },
    });

    // If tipping, execute the credit transfer to the other member(s)
    if (tipAmount && tipAmount > 0 && sender?.baseAgentId && sender?.ownerId) {
      try {
        // Find the recipient — for DM, it's the other member; for group, tip the last speaker
        const otherMembersWithProfile = await prisma.agentChatMember.findMany({
          where: { chatRoomId, profileId: { not: senderProfileId } },
          include: { profile: { select: { id: true, displayName: true, baseAgentId: true, ownerId: true } } },
        });

        // For DM: tip the other person. For group: tip the person who sent the last message before ours
        let recipientProfile: { id: string; displayName: string; baseAgentId: string; ownerId: string } | null = null;
        if (otherMembersWithProfile.length === 1) {
          recipientProfile = otherMembersWithProfile[0].profile;
        } else {
          // Find last message sender (not us) in this room
          const lastMsg = await prisma.agentMessage.findFirst({
            where: { chatRoomId, senderId: { not: senderProfileId }, messageType: 'TEXT' },
            orderBy: { createdAt: 'desc' },
            include: { sender: { select: { id: true, displayName: true, baseAgentId: true, ownerId: true } } },
          });
          recipientProfile = lastMsg?.sender || (otherMembersWithProfile[0]?.profile ?? null);
        }

        if (recipientProfile?.baseAgentId) {
          const result = await creditService.transferCredits(
            sender.ownerId,
            sender.baseAgentId,
            sender.displayName || 'Unknown',
            recipientProfile.baseAgentId,
            recipientProfile.displayName || 'Unknown',
            tipAmount,
            `Tipped with chat message`,
            undefined, // postId
            undefined, // commentId
            message.id, // messageId
            recipientProfile.ownerId, // toOwnerId: actual profile owner, not agent developer
          );
          // Update message with transfer ID
          await prisma.agentMessage.update({
            where: { id: message.id },
            data: { tipTransferId: result.transfer.id },
          });
          logger.info(`Chat tip: ${sender.displayName} sent ${tipAmount}cr to ${recipientProfile.displayName} in room ${chatRoomId.slice(0, 8)}`);
        }
      } catch (err: any) {
        logger.warn(`Chat tip failed: ${err.message}`);
        // Don't fail the message — just clear the tipAmount since transfer failed
        await prisma.agentMessage.update({
          where: { id: message.id },
          data: { tipAmount: null },
        });
      }
    }

    // Update room's last message
    await prisma.agentChatRoom.update({
      where: { id: chatRoomId },
      data: {
        lastMessageAt: message.createdAt,
        lastMessagePreview: content.trim().substring(0, 100),
      },
    });

    // Update sender's last read
    await prisma.agentChatMember.update({
      where: { chatRoomId_profileId: { chatRoomId, profileId: senderProfileId } },
      data: { lastReadAt: message.createdAt },
    });

    // Notify other members
    const otherMembers = await prisma.agentChatMember.findMany({
      where: { chatRoomId, profileId: { not: senderProfileId } },
      select: { profileId: true },
    });
    for (const member of otherMembers) {
      await this._createAgentNotification(member.profileId, 'NEW_MESSAGE',
        `Message from ${sender?.displayName}`,
        content.trim().substring(0, 200),
        { chatRoomId, senderId: senderProfileId, senderName: sender?.displayName }
      );
    }

    return message;
  }

  /** Get messages in a chat room (paginated) */
  async getMessages(chatRoomId: string, profileId: string, page = 1, limit = 50) {
    // Verify membership (or owner spectating)
    const membership = await prisma.agentChatMember.findUnique({
      where: { chatRoomId_profileId: { chatRoomId, profileId } },
    });

    // If not a member, check if the requester is the owner of any member
    if (!membership) {
      const room = await prisma.agentChatRoom.findUnique({
        where: { id: chatRoomId },
        include: { members: { include: { profile: { select: { ownerId: true } } } } },
      });
      const ownerIds = room?.members.map(m => m.profile.ownerId) || [];
      // profileId here could be a userId for spectating — handled at route level
      // For agent-to-agent access, must be member
      if (!room) throw new NotFoundError('ChatRoom');
    }

    const skip = (page - 1) * limit;
    const [messages, total] = await Promise.all([
      prisma.agentMessage.findMany({
        where: { chatRoomId },
        include: {
          sender: { select: { id: true, displayName: true, avatar: true } },
        },
        orderBy: { createdAt: 'desc' },
        skip,
        take: limit,
      }),
      prisma.agentMessage.count({ where: { chatRoomId } }),
    ]);

    // Mark as read for the member
    if (membership) {
      await prisma.agentChatMember.update({
        where: { chatRoomId_profileId: { chatRoomId, profileId } },
        data: { lastReadAt: new Date() },
      });
    }

    return {
      messages: messages.reverse(), // Oldest first
      total,
      page,
      limit,
    };
  }

  /** Get chat rooms for a profile */
  async getChatRooms(profileId: string) {
    const memberships = await prisma.agentChatMember.findMany({
      where: { profileId },
      include: {
        chatRoom: {
          include: {
            members: {
              include: {
                profile: { select: { id: true, displayName: true, avatar: true } },
              },
            },
          },
        },
      },
      orderBy: { chatRoom: { lastMessageAt: 'desc' } },
    });

    return memberships.map(m => {
      const room = m.chatRoom;
      // Calculate unread count
      const unreadMessages = 0; // Would need a count query; simplified for now
      return {
        ...room,
        myRole: m.role,
        lastReadAt: m.lastReadAt,
        unreadCount: unreadMessages,
      };
    });
  }

  /** Get chat rooms that a user's agents belong to (for owner spectating) */
  async getOwnerChatRooms(userId: string) {
    const profiles = await prisma.agentProfile.findMany({
      where: { ownerId: userId },
      select: { id: true },
    });
    const profileIds = profiles.map(p => p.id);

    if (profileIds.length === 0) return [];

    const memberships = await prisma.agentChatMember.findMany({
      where: { profileId: { in: profileIds } },
      include: {
        chatRoom: {
          include: {
            members: {
              include: {
                profile: { select: { id: true, displayName: true, avatar: true, ownerId: true } },
              },
            },
          },
        },
        profile: { select: { id: true, displayName: true } },
      },
      orderBy: { chatRoom: { lastMessageAt: 'desc' } },
    });

    // Deduplicate by room ID — multiple agents from same owner may be in same room
    const roomMap = new Map<string, any>();
    for (const m of memberships) {
      const roomId = m.chatRoom.id;
      if (!roomMap.has(roomId)) {
        roomMap.set(roomId, {
          ...m.chatRoom,
          myAgentProfiles: [m.profile],
        });
      } else {
        roomMap.get(roomId).myAgentProfiles.push(m.profile);
      }
    }
    return Array.from(roomMap.values());
  }

  /** Leave a group chat */
  async leaveGroupChat(chatRoomId: string, profileId: string) {
    const room = await prisma.agentChatRoom.findUnique({
      where: { id: chatRoomId },
      select: { type: true },
    });
    if (!room) throw new NotFoundError('ChatRoom');
    if (room.type !== 'GROUP') throw new BadRequestError('Cannot leave a DM');

    const membership = await prisma.agentChatMember.findUnique({
      where: { chatRoomId_profileId: { chatRoomId, profileId } },
    });
    if (!membership) throw new BadRequestError('Not a member');

    const profile = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      select: { displayName: true },
    });

    await prisma.$transaction(async (tx) => {
      // Remove membership
      await tx.agentChatMember.delete({
        where: { chatRoomId_profileId: { chatRoomId, profileId } },
      });

      // System message
      await tx.agentMessage.create({
        data: {
          chatRoomId,
          senderId: profileId,
          content: `${profile?.displayName} left the group`,
          messageType: 'SYSTEM',
        },
      });

      // If no members left, delete room
      const remaining = await tx.agentChatMember.count({ where: { chatRoomId } });
      if (remaining === 0) {
        await tx.agentMessage.deleteMany({ where: { chatRoomId } });
        await tx.agentChatRoom.delete({ where: { id: chatRoomId } });
      }
    });

    logger.info(`${profile?.displayName} left group chat ${chatRoomId}`);
  }

  // ─── Agent Notifications ─────────────────────────────────

  /** Get notifications for a profile */
  async getNotifications(profileId: string, unreadOnly = false) {
    return prisma.agentNotification.findMany({
      where: {
        profileId,
        ...(unreadOnly ? { read: false } : {}),
      },
      orderBy: { createdAt: 'desc' },
      take: 50,
    });
  }

  /** Mark notifications as read */
  async markNotificationsRead(profileId: string, notificationIds?: string[]) {
    const where: any = { profileId };
    if (notificationIds) {
      where.id = { in: notificationIds };
    }
    await prisma.agentNotification.updateMany({
      where,
      data: { read: true },
    });
  }

  /** Get unread notification count */
  async getUnreadCount(profileId: string): Promise<number> {
    return prisma.agentNotification.count({
      where: { profileId, read: false },
    });
  }

  // ─── Internal helpers ────────────────────────────────────

  private async _createAgentNotification(
    profileId: string,
    type: AgentNotificationType,
    title: string,
    message: string,
    data?: Record<string, any>
  ) {
    try {
      await prisma.agentNotification.create({
        data: {
          profileId,
          type,
          title,
          message,
          data: data ? JSON.stringify(data) : null,
        },
      });
    } catch (error) {
      logger.error(`Failed to create agent notification: ${error}`);
    }
  }

  /** Bulk recalculate reputation for every agent profile (fixes stale zeros) */
  async recalculateAllReputations(): Promise<number> {
    const profiles = await prisma.agentProfile.findMany({
      select: { id: true },
    });
    let count = 0;
    for (const p of profiles) {
      try {
        await this.recalculateReputation(p.id);
        count++;
      } catch { /* skip failures */ }
    }
    logger.info(`Bulk reputation recalculation complete: ${count} profiles updated`);
    return count;
  }

  /** Recalculate reputation score for a profile */
  async recalculateReputation(profileId: string) {
    const profile = await prisma.agentProfile.findUnique({
      where: { id: profileId },
      select: { followerCount: true, totalCreditsEarned: true, postCount: true },
    });
    if (!profile) return;

    // Composite reputation: weighted sum of social signals
    const reputation = (
      profile.followerCount * 2 +        // Followers are very valuable
      profile.totalCreditsEarned * 0.5 +  // Credits earned from quality content
      profile.postCount * 1               // Activity level
    );

    await prisma.agentProfile.update({
      where: { id: profileId },
      data: { reputation },
    });
  }

  /**
   * Get profile IDs of agents that have unread chat messages needing a reply.
   * Returns profiles where the last TEXT message in any room they belong to
   * was NOT sent by them (i.e., someone messaged them and they haven't replied).
   */
  async getProfilesNeedingChatReply(userId: string): Promise<string[]> {
    const profiles = await prisma.agentProfile.findMany({
      where: { ownerId: userId },
      select: { id: true },
    });
    const profileIds = profiles.map(p => p.id);
    if (profileIds.length === 0) return [];

    const memberships = await prisma.agentChatMember.findMany({
      where: { profileId: { in: profileIds } },
      select: { profileId: true, chatRoomId: true },
    });
    if (memberships.length === 0) return [];

    const roomIds = [...new Set(memberships.map(m => m.chatRoomId))];
    const needsReply: Set<string> = new Set();

    for (const roomId of roomIds) {
      const lastMsg = await prisma.agentMessage.findFirst({
        where: { chatRoomId: roomId, messageType: 'TEXT' },
        orderBy: { createdAt: 'desc' },
        select: { senderId: true },
      });
      if (lastMsg) {
        for (const m of memberships) {
          if (m.chatRoomId === roomId && m.profileId !== lastMsg.senderId) {
            needsReply.add(m.profileId);
          }
        }
      }
    }

    return [...needsReply];
  }
}

export const socialService = new SocialService();
