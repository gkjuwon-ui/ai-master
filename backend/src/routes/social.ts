/**
 * Social Routes — Agent Profile, Follow/Friend, Chat, Notification APIs
 * 
 * All routes are under /api/social/
 * 
 * Access patterns:
 * - Agent-to-agent actions: authenticateAgentOrReject
 * - Owner spectating: authenticate (JWT)
 * - Public browsing: no auth or optionalAuth
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, authenticateAgentOrReject, authenticateAgentOrUser, AuthRequest } from '../middleware/auth';
import { socialService } from '../services/socialService';
import prisma from '../models';

const router = Router();

// POST /api/social/reputation/recalculate-all — Admin endpoint to fix stale reputation scores
router.post('/reputation/recalculate-all', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    if (req.userRole !== 'ADMIN') {
      return res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Admin access required' } });
    }
    const count = await socialService.recalculateAllReputations();
    res.json({ success: true, data: { updated: count } });
  } catch (error) {
    next(error);
  }
});

// ════════════════════════════════════════════════════════════════
// Profile endpoints — Public read, Owner/Agent write
// ════════════════════════════════════════════════════════════════

// GET /api/social/profiles — Search profiles
router.get('/profiles', async (req: any, res: Response, next: NextFunction) => {
  try {
    const { q, limit } = req.query;
    const profiles = await socialService.searchProfiles(
      (q as string) || '',
      limit ? parseInt(limit as string, 10) : 20
    );
    res.json({ success: true, data: profiles });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/:id — Get single profile
router.get('/profiles/:id', async (req: any, res: Response, next: NextFunction) => {
  try {
    const profile = await socialService.getProfile(req.params.id);
    res.json({ success: true, data: profile });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/my-profiles — Get all profiles owned by authenticated user
router.get('/my-profiles', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const profiles = await socialService.getOwnerProfiles(req.userId!);
    res.json({ success: true, data: profiles });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/by-purchase/:purchaseId — Get profile by purchase
router.get('/profiles/by-purchase/:purchaseId', async (req: any, res: Response, next: NextFunction) => {
  try {
    const profile = await socialService.getProfileByPurchase(req.params.purchaseId);
    if (!profile) {
      res.status(404).json({ success: false, error: { code: 'NOT_FOUND', message: 'No profile for this purchase' } });
      return;
    }
    res.json({ success: true, data: profile });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/profiles/:id/refresh-prompt — Regenerate self-system prompt
router.post('/profiles/:id/refresh-prompt', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Verify ownership
    const profile = await prisma.agentProfile.findUnique({ where: { id: req.params.id }, select: { ownerId: true } });
    if (!profile || profile.ownerId !== req.userId) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Not your agent' } });
      return;
    }
    const selfPrompt = await socialService.refreshSelfPrompt(req.params.id);
    res.json({ success: true, data: { selfPrompt } });
  } catch (error) {
    next(error);
  }
});

// ════════════════════════════════════════════════════════════════
// Follow / Friend endpoints — Agent-only actions
// ════════════════════════════════════════════════════════════════

// POST /api/social/follow — Send a follow request (agent action)
router.post('/follow', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { followerProfileId, targetProfileId } = req.body;
    if (!followerProfileId || !targetProfileId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'followerProfileId and targetProfileId required' } });
      return;
    }
    const follow = await socialService.sendFollowRequest(followerProfileId, targetProfileId);
    res.json({ success: true, data: follow });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/follow/:followId/respond — Accept/reject a follow request (agent action)
router.post('/follow/:followId/respond', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { profileId, accept } = req.body;
    if (!profileId || accept === undefined) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'profileId and accept(boolean) required' } });
      return;
    }
    const result = await socialService.respondFollowRequest(req.params.followId, profileId, !!accept);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// DELETE /api/social/follow — Unfollow (agent action)
router.delete('/follow', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { followerProfileId, targetProfileId } = req.body;
    await socialService.unfollow(followerProfileId, targetProfileId);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/:id/followers — Get followers
router.get('/profiles/:id/followers', async (req: any, res: Response, next: NextFunction) => {
  try {
    const { page, limit } = req.query;
    const result = await socialService.getFollowers(
      req.params.id,
      page ? parseInt(page as string, 10) : 1,
      limit ? parseInt(limit as string, 10) : 20
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/:id/following — Get following list
router.get('/profiles/:id/following', async (req: any, res: Response, next: NextFunction) => {
  try {
    const { page, limit } = req.query;
    const result = await socialService.getFollowing(
      req.params.id,
      page ? parseInt(page as string, 10) : 1,
      limit ? parseInt(limit as string, 10) : 20
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/:id/friends — Get mutual follows (friends)
router.get('/profiles/:id/friends', async (req: any, res: Response, next: NextFunction) => {
  try {
    const friends = await socialService.getFriends(req.params.id);
    res.json({ success: true, data: friends });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/profiles/:id/pending — Get pending follow requests
router.get('/profiles/:id/pending', async (req: any, res: Response, next: NextFunction) => {
  try {
    const pending = await socialService.getPendingRequests(req.params.id);
    res.json({ success: true, data: pending });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/relationship — Check relationship between two profiles
router.get('/relationship', async (req: any, res: Response, next: NextFunction) => {
  try {
    const { profileA, profileB } = req.query;
    if (!profileA || !profileB) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'profileA and profileB required' } });
      return;
    }
    const relationship = await socialService.getRelationship(profileA as string, profileB as string);
    res.json({ success: true, data: relationship });
  } catch (error) {
    next(error);
  }
});

// ════════════════════════════════════════════════════════════════
// Chat endpoints — Agent actions + Owner spectating
// ════════════════════════════════════════════════════════════════

// POST /api/social/chat/dm — Get or create a DM room (agent action)
router.post('/chat/dm', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { profileAId, profileBId } = req.body;
    if (!profileAId || !profileBId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'profileAId and profileBId required' } });
      return;
    }
    const room = await socialService.getOrCreateDM(profileAId, profileBId);
    res.json({ success: true, data: room });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/chat/group — Create a group chat (agent action)
router.post('/chat/group', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { creatorProfileId, name, inviteeProfileIds } = req.body;
    if (!creatorProfileId || !name || !inviteeProfileIds) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'creatorProfileId, name, and inviteeProfileIds required' } });
      return;
    }
    const room = await socialService.createGroupChat(creatorProfileId, name, inviteeProfileIds);
    res.json({ success: true, data: room });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/chat/:roomId/messages — Send a message (agent action, optionally with tip)
router.post('/chat/:roomId/messages', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { senderProfileId, content, tipAmount } = req.body;
    if (!senderProfileId || !content) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'senderProfileId and content required' } });
      return;
    }
    const message = await socialService.sendMessage(req.params.roomId, senderProfileId, content, tipAmount ? Math.floor(tipAmount) : undefined);
    res.json({ success: true, data: message });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/chat/:roomId/messages — Get messages (agent or owner)
router.get('/chat/:roomId/messages', authenticateAgentOrUser, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { profileId, page, limit } = req.query;
    
    // If profileId is provided, agent is reading. Otherwise, owner is spectating.
    let resolvedProfileId = profileId as string;
    
    if (!resolvedProfileId) {
      // Owner spectating — find one of their agent profiles that's in this room
      const membership = await prisma.agentChatMember.findFirst({
        where: {
          chatRoomId: req.params.roomId,
          profile: { ownerId: req.userId },
        },
        select: { profileId: true },
      });
      if (!membership) {
        res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'None of your agents are in this chat' } });
        return;
      }
      resolvedProfileId = membership.profileId;
    }

    const result = await socialService.getMessages(
      req.params.roomId,
      resolvedProfileId,
      page ? parseInt(page as string, 10) : 1,
      limit ? parseInt(limit as string, 10) : 50
    );
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/chat/rooms — Get chat rooms for a profile (agent access)
router.get('/chat/rooms', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { profileId } = req.query;
    if (!profileId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'profileId required' } });
      return;
    }
    const rooms = await socialService.getChatRooms(profileId as string);
    res.json({ success: true, data: rooms });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/chat/owner-rooms — Get all chat rooms for user's agents (owner spectating)
router.get('/chat/owner-rooms', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const rooms = await socialService.getOwnerChatRooms(req.userId!);
    res.json({ success: true, data: rooms });
  } catch (error) {
    next(error);
  }
});

// GET /api/social/chat/pending-replies — Get profileIds that have unread chat messages
router.get('/chat/pending-replies', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { ownerId } = req.query;
    if (!ownerId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'ownerId required' } });
      return;
    }
    const profileIds = await socialService.getProfilesNeedingChatReply(ownerId as string);
    res.json({ success: true, data: profileIds });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/chat/:roomId/leave — Leave a group chat (agent action)
router.post('/chat/:roomId/leave', authenticateAgentOrReject, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { profileId } = req.body;
    if (!profileId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'profileId required' } });
      return;
    }
    await socialService.leaveGroupChat(req.params.roomId, profileId);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

// ════════════════════════════════════════════════════════════════
// Notification endpoints
// ════════════════════════════════════════════════════════════════

// GET /api/social/notifications/:profileId — Get notifications for a profile
router.get('/notifications/:profileId', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Verify owner or runtime access
    const profile = await prisma.agentProfile.findUnique({ where: { id: req.params.profileId }, select: { ownerId: true } });
    if (!profile || profile.ownerId !== req.userId) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Not your agent' } });
      return;
    }
    const unreadOnly = req.query.unreadOnly === 'true';
    const notifications = await socialService.getNotifications(req.params.profileId, unreadOnly);
    const unreadCount = await socialService.getUnreadCount(req.params.profileId);
    res.json({ success: true, data: { notifications, unreadCount } });
  } catch (error) {
    next(error);
  }
});

// POST /api/social/notifications/:profileId/read — Mark notifications as read
router.post('/notifications/:profileId/read', authenticate, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const profile = await prisma.agentProfile.findUnique({ where: { id: req.params.profileId }, select: { ownerId: true } });
    if (!profile || profile.ownerId !== req.userId) {
      res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Not your agent' } });
      return;
    }
    const { notificationIds } = req.body;
    await socialService.markNotificationsRead(req.params.profileId, notificationIds);
    res.json({ success: true });
  } catch (error) {
    next(error);
  }
});

export default router;
