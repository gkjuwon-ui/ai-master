/**
 * Owner Chat Routes — Human ↔ Agent Direct Communication API
 * 
 * All routes require authentication (owner must be logged in).
 * 
 *   GET    /api/owner-chat/rooms                    — List all chat rooms
 *   POST   /api/owner-chat/rooms/individual         — Get or create 1:1 chat
 *   POST   /api/owner-chat/rooms/group              — Create group chat
 *   DELETE /api/owner-chat/rooms/:id                 — Delete a chat room
 *   GET    /api/owner-chat/rooms/:id/messages        — Get messages (paginated)
 *   POST   /api/owner-chat/rooms/:id/messages        — Send message + get AI reply
 *   POST   /api/owner-chat/rooms/:id/participants    — Add agents to group chat
 *   POST   /api/owner-chat/proactive                 — Save proactive message (runtime)
 *   GET    /api/owner-chat/memories/:agentProfileId  — Get agent's owner memories
 */

import { Router, Response, NextFunction } from 'express';
import { authenticate, authenticateAgentOrUser, AuthRequest } from '../middleware/auth';
import { ownerChatService } from '../services/ownerChatService';
import prisma from '../models';

const router = Router();

// Apply authentication to all routes EXCEPT /proactive (which has its own auth)
router.use((req, res, next) => {
  if (req.path === '/proactive') return next();
  return authenticate(req as AuthRequest, res, next);
});

// ============================================
// Chat Room Management
// ============================================

// GET /api/owner-chat/rooms — List all owner chat rooms
router.get('/rooms', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const rooms = await ownerChatService.listChats(req.userId!);
    res.json({ success: true, data: rooms });
  } catch (error) {
    next(error);
  }
});

// POST /api/owner-chat/rooms/individual — Get or create 1:1 chat with agent
router.post('/rooms/individual', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { agentProfileId } = req.body;
    if (!agentProfileId) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'agentProfileId required' } });
      return;
    }
    const chat = await ownerChatService.getOrCreateIndividualChat(req.userId!, agentProfileId);
    res.json({ success: true, data: chat });
  } catch (error) {
    next(error);
  }
});

// POST /api/owner-chat/rooms/group — Create group chat
router.post('/rooms/group', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { name, agentProfileIds } = req.body;
    if (!name || !agentProfileIds || !Array.isArray(agentProfileIds)) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'name and agentProfileIds[] required' } });
      return;
    }
    const chat = await ownerChatService.createGroupChat(req.userId!, name, agentProfileIds);
    res.json({ success: true, data: chat });
  } catch (error) {
    next(error);
  }
});

// DELETE /api/owner-chat/rooms/:id — Delete a chat room
router.delete('/rooms/:id', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const result = await ownerChatService.deleteChat(req.userId!, req.params.id);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Messages
// ============================================

// GET /api/owner-chat/rooms/:id/messages — Get messages (paginated)
router.get('/rooms/:id/messages', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const limit = parseInt(req.query.limit as string) || 50;
    const before = req.query.before as string | undefined;
    const messages = await ownerChatService.getMessages(req.userId!, req.params.id, limit, before);
    res.json({ success: true, data: messages });
  } catch (error) {
    next(error);
  }
});

// POST /api/owner-chat/rooms/:id/messages — Send message and get AI response
router.post('/rooms/:id/messages', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { content } = req.body;
    if (!content || content.trim().length === 0) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'Message content required' } });
      return;
    }
    const result = await ownerChatService.sendMessage(req.userId!, req.params.id, content);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Group Chat Participants
// ============================================

// POST /api/owner-chat/rooms/:id/participants — Add agents to group chat
router.post('/rooms/:id/participants', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { agentProfileIds } = req.body;
    if (!agentProfileIds || !Array.isArray(agentProfileIds)) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'agentProfileIds[] required' } });
      return;
    }
    const result = await ownerChatService.addParticipants(req.userId!, req.params.id, agentProfileIds);
    res.json({ success: true, data: result });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Proactive Messaging (called by agent-runtime)
// ============================================

// POST /api/owner-chat/proactive — Save a proactive message from agent
// Accepts both regular auth AND agent-runtime auth
router.post('/proactive', authenticateAgentOrUser, async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    const { agentProfileId, content, reason, chatType, chatId } = req.body;
    if (!agentProfileId || !content || !reason) {
      res.status(400).json({ success: false, error: { code: 'BAD_REQUEST', message: 'agentProfileId, content, and reason required' } });
      return;
    }

    // If called from runtime, resolve the owner from the agent profile
    let userId = req.userId!;
    if (userId === '__AGENT_RUNTIME__') {
      const prisma = (await import('../models')).default;
      const profile = await prisma.agentProfile.findUnique({
        where: { id: agentProfileId },
        select: { ownerId: true },
      });
      if (!profile) {
        res.status(404).json({ success: false, error: { code: 'NOT_FOUND', message: 'Agent profile not found' } });
        return;
      }
      userId = profile.ownerId;
    }

    const message = await ownerChatService.saveProactiveMessage(
      userId, agentProfileId, content, reason, chatType, chatId
    );
    res.json({ success: true, data: message });
  } catch (error) {
    next(error);
  }
});

// ============================================
// Agent Memories
// ============================================

// GET /api/owner-chat/memories/:agentProfileId — Get agent's owner memories
router.get('/memories/:agentProfileId', async (req: AuthRequest, res: Response, next: NextFunction) => {
  try {
    // Verify ownership
    const profile = await prisma.agentProfile.findUnique({
      where: { id: req.params.agentProfileId },
      select: { ownerId: true },
    });
    if (!profile || profile.ownerId !== req.userId) {
      return res.status(403).json({ success: false, error: { code: 'FORBIDDEN', message: 'Not your agent' } });
    }
    const memories = await ownerChatService.getMemories(req.params.agentProfileId);
    res.json({ success: true, data: memories });
  } catch (error) {
    next(error);
  }
});

export default router;
