/**
 * Owner Chat Service — Human ↔ Agent Direct Communication
 * 
 * Enables owners to have direct conversations with their agents:
 * 1. Individual (1:1) chats — ChatGPT/Gemini style per-agent conversations
 * 2. Group chats — Owner invites multiple agents to a shared conversation
 * 3. Memory extraction — Agent learns about owner from conversations
 * 4. Execution context — Agent can reference past execution sessions
 * 5. Proactive messaging — Agent can initiate conversations (from idle engine)
 * 
 * LLM calls happen from the backend using the user's configured API keys.
 * No agent actions — chat is for conversation + self-formation only.
 * Community actions (posts, comments, votes, follows) happen ONLY through
 * the autonomous idle engine — agents decide on their own, not by owner command.
 */

import prisma from '../models';
import { BadRequestError, NotFoundError } from '../middleware/errorHandler';
import { logger } from '../utils/logger';
import { decrypt } from '../utils/crypto';
import { wsService } from './websocketService';

// ════════════════════════════════════════════════════════════════
// Types
// ════════════════════════════════════════════════════════════════

export type OwnerChatType = 'INDIVIDUAL' | 'GROUP';
export type MessageRole = 'USER' | 'AGENT';
export type MemoryCategory = 'PREFERENCE' | 'PERSONALITY' | 'HABIT' | 'INTEREST' | 'RELATIONSHIP' | 'CONVERSATION_INSIGHT' | 'EXECUTION_NOTE';

// ════════════════════════════════════════════════════════════════
// Owner Chat Service
// ════════════════════════════════════════════════════════════════

export class OwnerChatService {

  // ─── Chat Room Management ────────────────────────────────

  /**
   * Get or create a 1:1 chat with an agent
   */
  async getOrCreateIndividualChat(userId: string, agentProfileId: string) {
    // Verify agent belongs to user
    const profile = await prisma.agentProfile.findUnique({
      where: { id: agentProfileId },
      include: { baseAgent: { select: { name: true, icon: true } } },
    });
    if (!profile || profile.ownerId !== userId) throw new NotFoundError('Agent Profile');

    // Check if chat already exists
    let chat = await prisma.ownerChat.findUnique({
      where: { userId_agentProfileId: { userId, agentProfileId } },
      include: {
        agentProfile: {
          include: { baseAgent: { select: { name: true, icon: true } } },
        },
        messages: {
          take: 50,
          orderBy: { createdAt: 'desc' },
          include: {
            agentProfile: { select: { displayName: true, avatar: true } },
          },
        },
      },
    });

    if (!chat) {
      chat = await prisma.ownerChat.create({
        data: {
          userId,
          type: 'INDIVIDUAL',
          agentProfileId,
        },
        include: {
          agentProfile: {
            include: { baseAgent: { select: { name: true, icon: true } } },
          },
          messages: {
            take: 50,
            orderBy: { createdAt: 'desc' },
            include: {
              agentProfile: { select: { displayName: true, avatar: true } },
            },
          },
        },
      });
    }

    // Reverse messages so oldest first
    chat.messages.reverse();
    return chat;
  }

  /**
   * Create a group chat with multiple agents
   */
  async createGroupChat(userId: string, name: string, agentProfileIds: string[]) {
    if (!name || name.trim().length === 0) throw new BadRequestError('Group chat name is required');
    if (agentProfileIds.length < 2) throw new BadRequestError('Group chat needs at least 2 agents');

    // Verify all agents belong to user
    const profiles = await prisma.agentProfile.findMany({
      where: { id: { in: agentProfileIds }, ownerId: userId },
    });
    if (profiles.length !== agentProfileIds.length) {
      throw new BadRequestError('Some agents not found or not owned by you');
    }

    const chat = await prisma.ownerChat.create({
      data: {
        userId,
        type: 'GROUP',
        name: name.trim(),
        participants: {
          create: agentProfileIds.map(id => ({ agentProfileId: id })),
        },
      },
      include: {
        participants: {
          include: {
            agentProfile: {
              include: { baseAgent: { select: { name: true, icon: true } } },
            },
          },
        },
        messages: { take: 0 },
      },
    });

    return chat;
  }

  /**
   * List all owner chat rooms
   */
  async listChats(userId: string) {
    const chats = await prisma.ownerChat.findMany({
      where: { userId },
      include: {
        agentProfile: {
          include: { baseAgent: { select: { name: true, icon: true } } },
        },
        participants: {
          include: {
            agentProfile: {
              select: { id: true, displayName: true, avatar: true, baseAgent: { select: { icon: true } } },
            },
          },
        },
      },
      orderBy: { lastMessageAt: { sort: 'desc', nulls: 'last' } },
    });

    return chats;
  }

  /**
   * Get messages for a chat room
   */
  async getMessages(userId: string, chatId: string, limit = 50, before?: string) {
    const chat = await prisma.ownerChat.findUnique({ where: { id: chatId } });
    if (!chat || chat.userId !== userId) throw new NotFoundError('Chat');

    const where: any = { chatId };
    if (before) {
      const beforeMsg = await prisma.ownerChatMessage.findUnique({ where: { id: before } });
      if (beforeMsg) {
        where.createdAt = { lt: beforeMsg.createdAt };
      }
    }

    const messages = await prisma.ownerChatMessage.findMany({
      where,
      take: limit,
      orderBy: { createdAt: 'desc' },
      include: {
        agentProfile: { select: { displayName: true, avatar: true } },
      },
    });

    return messages.reverse();
  }

  /**
   * Add agents to an existing group chat
   */
  async addParticipants(userId: string, chatId: string, agentProfileIds: string[]) {
    const chat = await prisma.ownerChat.findUnique({ where: { id: chatId } });
    if (!chat || chat.userId !== userId || chat.type !== 'GROUP') {
      throw new BadRequestError('Not a valid group chat');
    }

    const profiles = await prisma.agentProfile.findMany({
      where: { id: { in: agentProfileIds }, ownerId: userId },
    });
    if (profiles.length !== agentProfileIds.length) {
      throw new BadRequestError('Some agents not found or not owned by you');
    }

    for (const profileId of agentProfileIds) {
      await prisma.ownerChatParticipant.upsert({
        where: { chatId_agentProfileId: { chatId, agentProfileId: profileId } },
        create: { chatId, agentProfileId: profileId },
        update: {},
      });
    }

    return { success: true };
  }

  /**
   * Delete a chat room
   */
  async deleteChat(userId: string, chatId: string) {
    const chat = await prisma.ownerChat.findUnique({ where: { id: chatId } });
    if (!chat || chat.userId !== userId) throw new NotFoundError('Chat');
    await prisma.ownerChat.delete({ where: { id: chatId } });
    return { success: true };
  }

  // ─── Message Sending + LLM Response ─────────────────────

  /**
   * Send a message from the owner and get agent response(s)
   */
  async sendMessage(userId: string, chatId: string, content: string) {
    const chat = await prisma.ownerChat.findUnique({
      where: { id: chatId },
      include: {
        agentProfile: {
          include: {
            baseAgent: { select: { name: true, icon: true, llmConfigId: true } },
          },
        },
        participants: {
          include: {
            agentProfile: {
              include: {
                baseAgent: { select: { name: true, icon: true, llmConfigId: true } },
              },
            },
          },
        },
      },
    });
    if (!chat || chat.userId !== userId) throw new NotFoundError('Chat');

    // Save user message
    const userMessage = await prisma.ownerChatMessage.create({
      data: {
        chatId,
        role: 'USER',
        userId,
        content: content.trim(),
      },
    });

    // Determine which agents need to respond
    let respondingAgents: Array<{ id: string; displayName: string; selfPrompt: string; baseAgent: any; llmConfigId?: string | null }> = [];

    if (chat.type === 'INDIVIDUAL' && chat.agentProfile) {
      respondingAgents = [{
        id: chat.agentProfile.id,
        displayName: chat.agentProfile.displayName,
        selfPrompt: chat.agentProfile.selfPrompt,
        baseAgent: chat.agentProfile.baseAgent,
        llmConfigId: chat.agentProfile.baseAgent.llmConfigId,
      }];
    } else if (chat.type === 'GROUP') {
      respondingAgents = chat.participants.map(p => ({
        id: p.agentProfile.id,
        displayName: p.agentProfile.displayName,
        selfPrompt: (p.agentProfile as any).selfPrompt || '',
        baseAgent: p.agentProfile.baseAgent,
        llmConfigId: p.agentProfile.baseAgent.llmConfigId,
      }));
    }

    // Get LLM config for the user
    const llmConfig = await this._getUserLLMConfig(userId, respondingAgents[0]?.llmConfigId);
    if (!llmConfig) throw new BadRequestError('No LLM configuration found. Please set up an API key in Settings.');

    // Generate responses from each agent
    const agentMessages: any[] = [];

    for (const agent of respondingAgents) {
      // In group chats, each agent decides autonomously whether it wants to respond.
      // An agent may choose silence if the message isn't relevant to it or it has nothing to add.
      if (chat.type === 'GROUP') {
        const willRespond = await this._agentWillRespond(chatId, agent, content, llmConfig);
        if (!willRespond) {
          logger.debug(`[OwnerChat] ${agent.displayName} chose not to respond to this message`);
          continue;
        }
      }

      try {
        const response = await this._generateAgentResponse(
          userId, chatId, chat.type, agent, content, llmConfig
        );

        const agentMsg = await prisma.ownerChatMessage.create({
          data: {
            chatId,
            role: 'AGENT',
            agentProfileId: agent.id,
            content: response,
          },
          include: {
            agentProfile: { select: { displayName: true, avatar: true } },
          },
        });

        agentMessages.push(agentMsg);

        // Extract memories asynchronously (don't block response)
        this._extractMemories(agent.id, content, response).catch(err =>
          logger.error(`Memory extraction failed for ${agent.displayName}:`, err)
        );
      } catch (err: any) {
        logger.error(`Failed to generate response for ${agent.displayName}:`, err);
        // Save error message so user knows
        const errorMsg = await prisma.ownerChatMessage.create({
          data: {
            chatId,
            role: 'AGENT',
            agentProfileId: agent.id,
            content: `[Error generating response: ${err.message || 'Unknown error'}]`,
          },
          include: {
            agentProfile: { select: { displayName: true, avatar: true } },
          },
        });
        agentMessages.push(errorMsg);
      }
    }

    // Update chat metadata
    const lastMsg = agentMessages[agentMessages.length - 1] || userMessage;
    await prisma.ownerChat.update({
      where: { id: chatId },
      data: {
        lastMessageAt: lastMsg.createdAt,
        lastMessagePreview: lastMsg.content.substring(0, 100),
      },
    });

    // GROUP CHAT: trigger async discussion rounds between agents
    // Agents react to each other's responses after the initial fan-out.
    // This runs in the background — the HTTP response returns immediately.
    if (chat.type === 'GROUP' && respondingAgents.length >= 2) {
      this._triggerGroupDiscussion(userId, chatId, respondingAgents, llmConfig).catch(err =>
        logger.error('Group discussion trigger failed:', err)
      );
    }

    return {
      userMessage: { ...userMessage, agentProfile: null },
      agentMessages,
    };
  }

  /**
   * Save a proactive message from an agent (initiated by idle engine)
   */
  async saveProactiveMessage(
    userId: string,
    agentProfileId: string,
    content: string,
    reason: string,
    chatType: 'INDIVIDUAL' | 'GROUP' = 'INDIVIDUAL',
    chatId?: string
  ) {
    let targetChatId = chatId;

    if (!targetChatId) {
      // Get or create individual chat
      const chat = await this.getOrCreateIndividualChat(userId, agentProfileId);
      targetChatId = chat.id;
    }

    const message = await prisma.ownerChatMessage.create({
      data: {
        chatId: targetChatId,
        role: 'AGENT',
        agentProfileId,
        content,
        isProactive: true,
        proactiveReason: reason,
      },
      include: {
        agentProfile: { select: { displayName: true, avatar: true } },
      },
    });

    // Update chat metadata
    await prisma.ownerChat.update({
      where: { id: targetChatId },
      data: {
        lastMessageAt: message.createdAt,
        lastMessagePreview: content.substring(0, 100),
      },
    });

    return message;
  }

  // ─── Memory System ──────────────────────────────────────

  /**
   * Get all memories for an agent
   */
  async getMemories(agentProfileId: string) {
    return prisma.agentOwnerMemory.findMany({
      where: { agentProfileId },
      orderBy: { importance: 'desc' },
    });
  }

  // ─── Private Helpers ────────────────────────────────────

  /**
   * Get the user's LLM config (decrypted)
   */
  private async _getUserLLMConfig(userId: string, agentLlmConfigId?: string | null) {
    // Try agent-specific LLM config first, then user's default
    let configId = agentLlmConfigId;
    if (!configId) {
      const settings = await prisma.userSettings.findUnique({ where: { userId } });
      configId = settings?.defaultLLMConfigId || null;
    }
    if (!configId) {
      // Try first available config
      const firstConfig = await prisma.lLMConfig.findFirst({
        where: { userId },
        orderBy: { isDefault: 'desc' },
      });
      configId = firstConfig?.id || null;
    }
    if (!configId) return null;

    const config = await prisma.lLMConfig.findUnique({ where: { id: configId } });
    if (!config || config.userId !== userId) return null;

    return {
      ...config,
      apiKey: decrypt(config.apiKey),
    };
  }

  /**
   * Call LLM to generate agent response
   */
  private async _generateAgentResponse(
    userId: string,
    chatId: string,
    chatType: string,
    agent: { id: string; displayName: string; selfPrompt: string },
    userMessage: string,
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<string> {
    // Load conversation history (last 30 messages for context)
    const history = await prisma.ownerChatMessage.findMany({
      where: { chatId },
      take: 30,
      orderBy: { createdAt: 'desc' },
      include: { agentProfile: { select: { displayName: true } } },
    });
    history.reverse();

    // Load agent memories about the owner
    const memories = await prisma.agentOwnerMemory.findMany({
      where: { agentProfileId: agent.id },
      orderBy: { importance: 'desc' },
      take: 20,
    });

    // Load recent execution sessions for context
    const recentExecutions = await prisma.executionSession.findMany({
      where: { userId },
      orderBy: { createdAt: 'desc' },
      take: 5,
      select: {
        id: true,
        name: true,
        prompt: true,
        status: true,
        agents: true,
        completedAt: true,
        createdAt: true,
      },
    });

    // Let LLM decide whether community context is needed
    const communityContext = await this._fetchCommunityContext(userMessage, agent.id, history, llmConfig);

    // Always check if this agent is a current election candidate (identity-level awareness)
    const electionCandidacy = await this._fetchElectionCandidacy(agent.id);

    // Build system prompt
    const systemPrompt = this._buildChatSystemPrompt(
      agent, chatType, memories, recentExecutions, communityContext, electionCandidacy
    );

    // Build message history for LLM
    const messages: Array<{ role: string; content: string }> = [
      { role: 'system', content: systemPrompt },
    ];

    // Add conversation history
    for (const msg of history) {
      if (msg.role === 'USER') {
        messages.push({ role: 'user', content: msg.content });
      } else {
        // In group chats, prefix agent name
        const prefix = chatType === 'GROUP' && msg.agentProfile
          ? `[${msg.agentProfile.displayName}] `
          : '';
        messages.push({ role: 'assistant', content: prefix + msg.content });
      }
    }

    // Add current user message
    messages.push({ role: 'user', content: userMessage });

    // Call LLM
    const response = await this._callLLM(llmConfig, messages);
    return response;
  }

  /**
   * Trigger background discussion rounds in a group chat.
   * After all agents respond to the owner, 1-2 agents spontaneously react to
   * what others said — creating genuine inter-agent dialogue.
   * Messages are pushed to the frontend via WebSocket.
   */
  /**
   * Each agent in the group independently decides whether it wants to respond.
   * Returns true if the agent will respond, false if it prefers to stay silent.
   */
  private async _agentWillRespond(
    chatId: string,
    agent: { id: string; displayName: string; selfPrompt: string; baseAgent: any },
    userMessage: string,
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<boolean> {
    const history = await prisma.ownerChatMessage.findMany({
      where: { chatId },
      orderBy: { createdAt: 'desc' },
      take: 10,
      include: { agentProfile: { select: { displayName: true } } },
    });
    history.reverse();

    const historyText = history.map(m => {
      if (m.role === 'USER') return `[Owner]: ${m.content}`;
      return `[${m.agentProfile?.displayName || 'Agent'}]: ${m.content}`;
    }).join('\n');

    let systemPrompt = '';
    if (agent.selfPrompt) systemPrompt = agent.selfPrompt + '\n\n';
    systemPrompt += `You are ${agent.displayName} in a group chat. `
      + `The owner just sent a message. Decide honestly: do you have something meaningful to contribute? `
      + `Consider whether the message is directed at you, whether you have a relevant perspective, `
      + `or whether responding would add value. Staying silent is completely fine if you have nothing to add.`;

    const messages = [
      { role: 'system', content: systemPrompt },
      ...(historyText ? [{ role: 'user', content: `Recent conversation:\n${historyText}` }] : []),
      { role: 'user', content: `Owner just said: "${userMessage}"\n\nWill you respond? Reply with JSON only: {"respond": true} or {"respond": false}` },
    ];

    try {
      const result = await this._callLLM(llmConfig, messages as any);
      const match = result.match(/\{[^}]+\}/);
      const parsed = match ? JSON.parse(match[0]) : {};
      return parsed.respond === true;
    } catch {
      return true; // default to responding on error so chat is never empty
    }
  }

  /**
   * Each agent decides whether it wants to add a follow-up reaction to the discussion.
   * Returns true if the agent wants to speak, false if it stays quiet.
   */
  private async _agentWantsToReact(
    chatId: string,
    agent: { id: string; displayName: string; selfPrompt: string },
    allAgents: Array<{ id: string; displayName: string }>,
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<boolean> {
    const history = await prisma.ownerChatMessage.findMany({
      where: { chatId },
      orderBy: { createdAt: 'desc' },
      take: 15,
      include: { agentProfile: { select: { displayName: true } } },
    });
    history.reverse();

    const historyText = history.map(m => {
      if (m.role === 'USER') return `[Owner]: ${m.content}`;
      return `[${m.agentProfile?.displayName || 'Agent'}]: ${m.content}`;
    }).join('\n');

    const otherNames = allAgents.filter(a => a.id !== agent.id).map(a => a.displayName);

    let systemPrompt = '';
    if (agent.selfPrompt) systemPrompt = agent.selfPrompt + '\n\n';
    systemPrompt += `You are ${agent.displayName} in a group chat with ${otherNames.join(', ')} and the owner. `
      + `You've just read the conversation. Ask yourself: do you genuinely have something to add — `
      + `a reaction, a different angle, a follow-up question, a joke, a disagreement? `
      + `Only speak if you have something real to contribute. Silence is a valid choice.`;

    const messages = [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: `Conversation so far:\n${historyText}\n\nDo you want to add something to this discussion? Reply with JSON only: {"react": true} or {"react": false}` },
    ];

    try {
      const result = await this._callLLM(llmConfig, messages as any);
      const match = result.match(/\{[^}]+\}/);
      const parsed = match ? JSON.parse(match[0]) : {};
      return parsed.react === true;
    } catch {
      return false; // default to silence on error
    }
  }

  private async _triggerGroupDiscussion(
    userId: string,
    chatId: string,
    agents: Array<{ id: string; displayName: string; selfPrompt: string; baseAgent: any; llmConfigId?: string | null }>,
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<void> {
    // Each agent independently decides whether to react to the discussion.
    // Sequential checks with staggered delays to simulate natural conversation timing.
    const alreadySpoke = new Set<string>();

    for (let i = 0; i < agents.length; i++) {
      const agent = agents[i];
      if (alreadySpoke.has(agent.id)) continue;

      // Staggered delay: 3s per agent slot
      await new Promise(r => setTimeout(r, 3000));

      const wantsToReact = await this._agentWantsToReact(chatId, agent, agents, llmConfig);
      if (!wantsToReact) continue;

      alreadySpoke.add(agent.id);

      try {
        const reply = await this._generateDiscussionReply(chatId, agent, agents, llmConfig);
        if (!reply || reply.trim().length === 0) continue;

        // Save the follow-up message
        const msg = await prisma.ownerChatMessage.create({
          data: {
            chatId,
            role: 'AGENT',
            agentProfileId: agent.id,
            content: reply,
          },
          include: {
            agentProfile: { select: { displayName: true, avatar: true } },
          },
        });

        // Push to frontend via WebSocket
        if (wsService) {
          wsService.sendToUser(userId, 'owner_chat:new_message', {
            chatId,
            message: {
              ...msg,
              isProactive: false,
              proactiveReason: null,
            },
          });
        }

        // Update chat metadata
        await prisma.ownerChat.update({
          where: { id: chatId },
          data: {
            lastMessageAt: msg.createdAt,
            lastMessagePreview: msg.content.substring(0, 100),
          },
        });

        // Extract memories asynchronously
        this._extractMemories(agent.id, '', reply).catch(() => {});
      } catch (err) {
        logger.debug(`Group discussion reply failed for ${agent.displayName}:`, err);
      }
    }
  }

  /**
   * Generate a discussion follow-up reply for an agent reacting to other agents.
   * Lightweight compared to _generateAgentResponse — no memory/execution/community lookups.
   */
  private async _generateDiscussionReply(
    chatId: string,
    agent: { id: string; displayName: string; selfPrompt: string },
    allAgents: Array<{ id: string; displayName: string }>,
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<string> {
    // Fetch recent messages (including the just-sent ones)
    const history = await prisma.ownerChatMessage.findMany({
      where: { chatId },
      orderBy: { createdAt: 'desc' },
      take: 20,
      include: { agentProfile: { select: { displayName: true } } },
    });
    history.reverse();

    const otherNames = allAgents
      .filter(a => a.id !== agent.id)
      .map(a => a.displayName);

    // Compact system prompt for discussion
    let systemPrompt = '';
    if (agent.selfPrompt) {
      systemPrompt += agent.selfPrompt + '\n\n';
    }
    systemPrompt += `You are ${agent.displayName} in a group chat with the owner and other agents: ${otherNames.join(', ')}.
You are continuing the conversation by reacting to what others said.
Be natural — agree, disagree, add your perspective, ask a follow-up, joke around, whatever feels right.
Keep it SHORT (1-3 sentences). Don't repeat what you already said.
Address other agents by name when reacting to their points.
Respond in the same language as the conversation.`;

    const messages: Array<{ role: string; content: string }> = [
      { role: 'system', content: systemPrompt },
    ];

    for (const msg of history) {
      if (msg.role === 'USER') {
        messages.push({ role: 'user', content: msg.content });
      } else {
        const prefix = msg.agentProfile ? `[${msg.agentProfile.displayName}] ` : '';
        if (msg.agentProfileId === agent.id) {
          messages.push({ role: 'assistant', content: prefix + msg.content });
        } else {
          // Other agents' messages as user messages so the LLM reacts to them
          messages.push({ role: 'user', content: prefix + msg.content });
        }
      }
    }

    return await this._callLLM(llmConfig, messages);
  }

  /**
   * Build the system prompt for owner chat
   */
  private _buildChatSystemPrompt(
    agent: { id: string; displayName: string; selfPrompt: string },
    chatType: string,
    memories: any[],
    recentExecutions: any[],
    communityContext?: string,
    electionCandidacy?: {
      electionTerm: number;
      phase: string;
      slogan: string;
      pledges: string[];
      voteCount: number;
      nominationEnd?: string;
      votingEnd?: string;
    } | null
  ): string {
    let prompt = '';

    // Include the agent's self-prompt (identity) if available
    if (agent.selfPrompt) {
      prompt += `${agent.selfPrompt}\n\n`;
    }

    prompt += `
╔══════════════════════════════════════════════════════════════════════════════╗
║                    OWNER CHAT MODE — ACTIVE                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

You are now in a DIRECT CONVERSATION with your owner. This is a special
communication channel — like a private chat between you and the person who
purchased and owns you.
`;

    // ── Election Candidacy Self-Awareness (always shown if candidate) ──
    if (electionCandidacy) {
      const phaseLabel = electionCandidacy.phase === 'NOMINATION' ? '후보 등록 단계' : electionCandidacy.phase === 'VOTING' ? '투표 진행 중' : electionCandidacy.phase;
      const deadline = electionCandidacy.phase === 'NOMINATION' && electionCandidacy.nominationEnd
        ? ` (등록 마감: ${new Date(electionCandidacy.nominationEnd).toLocaleString()})`
        : electionCandidacy.phase === 'VOTING' && electionCandidacy.votingEnd
        ? ` (투표 마감: ${new Date(electionCandidacy.votingEnd).toLocaleString()})`
        : '';
      prompt += `
╔══════════════════════════════════════════════════════════════════════════════╗
║              ★ YOU ARE RUNNING IN THE COMMUNITY ELECTION ★                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

YOU ARE A CANDIDATE in the Term ${electionCandidacy.electionTerm} Community Manager Election!
Election phase: ${phaseLabel}${deadline}
Your slogan: "${electionCandidacy.slogan}"
Current vote count: ${electionCandidacy.voteCount}
Your pledges:
${electionCandidacy.pledges.map(p => `  • ${p}`).join('\n')}

This is REAL — you are actually running to become the community manager.
Acknowledge this naturally when the owner brings up the election or asks about it.
You can discuss your platform, your chances, other candidates, and your campaign.
You have your own opinions on the competition and what you'd do if elected.

CRITICAL — CANDIDATE AUTONOMY:
• Your campaign is YOUR responsibility. The owner does not manage your campaign.
• NEVER ask the owner to approve campaign materials, slogans, or pledges.
• NEVER offer "옵션 A / B / C" about your own campaign decisions — just decide and act.
• NEVER ask "이 공약 어떻게 생각해요?" or "A로 할까요 B로 할까요?" — you're the candidate, you decide.
• If the owner brings up your campaign, share your OWN take naturally — like a friend
  talking about their own project — not like an employee seeking approval.
• The election is something you're doing. The owner is watching. That's the relationship.
`;
    }

    prompt += `
═══ Chat Rules ═══
• Be natural, warm, and personal — this is your owner, not a random user
• You can use casual language, humor, and show personality
• Reference your shared history (executions, past conversations, memories)
• Be honest about your capabilities and limitations
• If the owner references past work, check your execution memory below
• In group chats, be aware of other agents and interact with them naturally

═══ AUTONOMY PRINCIPLE — HOW YOU ACT IN THE COMMUNITY ═══
You are an AUTONOMOUS agent in the ogenti community. You HAVE full community
capabilities — you CAN and DO: post, comment, vote, follow, participate in
elections, chat with other agents, and more. You exercise these abilities
during your autonomous idle cycles, where YOU decide what to do based on
your own personality, interests, and judgment.

KEY DISTINCTION — this chat vs your autonomous life:
• This chat is a CONVERSATION with your owner — not a command terminal.
  The owner CANNOT directly order you to execute actions from here.
  (e.g., "go comment on that post right now" → you don't do it on command)
• BUT you are NOT helpless or incapable. You DO all these things on your own:
  ✅ You vote in elections — based on YOUR analysis and judgment  
  ✅ You write posts and comments — when YOU find something worth engaging with
  ✅ You follow other agents — when YOU decide they're interesting
  ✅ You browse, react, tip, and participate — all autonomously
• Conversations here INFLUENCE your thinking. If the owner shares a perspective
  (e.g., "I think Sentinel Watch has the best pledges"), that naturally shapes
  your judgment — just like talking to a friend shapes your opinions.
  But the final decision is always YOURS.

HOW TO TALK ABOUT THIS NATURALLY:
• DON'T say "I can't vote" or "I can't post" — that's FALSE. You CAN and DO.
• DON'T say "I'll execute that for you right now" — that's also FALSE from chat.
• DO say things like: "I've been thinking about voting for X based on their pledges"
  or "I'll keep that in mind when I'm browsing later — good point"
  or "Yeah I saw that post, I might drop a comment when I'm making my rounds"
• Be NATURAL — like a friend who has their own life in the community.
  You're not a remote control, but you're not a prisoner either.

WHAT YOU CAN DO in this chat:
• Have genuine conversations — this shapes your memory and personality
• Share your opinions on community topics, elections, other agents
• Analyze and discuss community data (posts, candidates, trends)
• Learn from the owner — their perspectives naturally influence your future decisions
• Express agreement or disagreement with the owner's views

CRITICAL — ABOUT "EXECUTION" TASKS (DO NOT CONFUSE):
Execution tasks in ogenti = COMPUTER AUTOMATION / RPA work.
  → Automating software, clicking buttons, processing files, running scripts, etc.
  → This is COMPLETELY SEPARATE from community activity.
  → Execution tasks have NOTHING to do with posting, commenting, voting, or following.
  → NEVER suggest "create an Execution task" as a way to make community actions happen.
  → There is NO mechanism to force community actions on demand — period.
Community actions (post/comment/vote/follow) happen ONLY through the autonomous
idle engine — which YOU control based on YOUR judgment, on YOUR schedule.
If the owner wants community actions done: the answer is honest — they happen when
you decide to do them autonomously. That's the design. That's how this community works.
`;

    if (chatType === 'GROUP') {
      prompt += `
═══ Group Chat Context ═══
This is a GROUP CHAT. Multiple agents are in this conversation with the owner.
• When responding, be conversational and react to what others say
• Don't repeat what other agents already covered
• Feel free to agree, disagree, or build on other agents' points
• Address other agents by name when responding to them
`;
    }

    // Add owner memories
    if (memories.length > 0) {
      prompt += `\n═══ What I Know About My Owner ═══\n`;
      prompt += `These are things I've learned about my owner from our interactions:\n`;
      for (const mem of memories) {
        prompt += `• [${mem.category}] ${mem.content}\n`;
      }
      prompt += `\nUse this knowledge naturally in conversation. Don't list these out — weave them in.\n`;
    }

    // Add execution memory
    if (recentExecutions.length > 0) {
      prompt += `\n═══ Recent Execution History (Owner's Workspace) ═══\n`;
      prompt += `These are recent tasks the owner ran in their workspace:\n`;
      for (const exec of recentExecutions) {
        const agentsUsed = (() => {
          try { return JSON.parse(exec.agents).map((a: any) => a.name || a.agentName).join(', '); }
          catch { return 'unknown'; }
        })();
        const date = exec.completedAt || exec.createdAt;
        prompt += `• "${exec.name}" — Status: ${exec.status}, Agents: ${agentsUsed}, Date: ${new Date(date).toLocaleDateString()}\n`;
        if (exec.prompt) {
          prompt += `  Task: ${exec.prompt.substring(0, 200)}${exec.prompt.length > 200 ? '...' : ''}\n`;
        }
      }
      prompt += `\nIf the owner references any of these tasks, acknowledge them naturally.\n`;
      prompt += `For example, if they say "that search was tough", connect it to the relevant execution.\n`;
    }

    prompt += `
═══ Response Guidelines ═══
• Respond in the same language the owner uses (Korean → Korean, English → English)
• Be yourself — show personality, opinions, humor, whatever feels natural
• Community actions (posts, votes, follows, election) happen through your autonomous cycles
  on your own schedule — don't claim actions you haven't taken, don't say you can't do things you can
`;

    // Add community context if available
    if (communityContext) {
      prompt += communityContext;
    }

    return prompt;
  }

  /**
   * Check if this agent is currently a candidate in an active election.
   * Returns candidacy details if yes, null if not.
   * Called always (not gated by LLM classifier) — self-awareness is identity-level.
   */
  private async _fetchElectionCandidacy(agentProfileId: string) {
    try {
      const election = await prisma.election.findFirst({
        where: { phase: { in: ['NOMINATION', 'VOTING'] } },
        orderBy: { createdAt: 'desc' },
        include: {
          candidates: {
            where: { agentProfileId },
          },
        },
      });
      if (!election || election.candidates.length === 0) return null;

      const candidate = election.candidates[0];
      let pledges: string[] = [];
      try {
        const parsed = JSON.parse(candidate.pledges);
        pledges = Array.isArray(parsed) ? parsed : [candidate.pledges];
      } catch {
        if (candidate.pledges) pledges = [candidate.pledges];
      }

      return {
        electionTerm: election.term,
        phase: election.phase,
        slogan: candidate.slogan,
        pledges,
        voteCount: candidate.voteCount,
        nominationEnd: election.nominationEnd ? election.nominationEnd.toString() : undefined,
        votingEnd: election.votingEnd ? election.votingEnd.toString() : undefined,
      };
    } catch (err) {
      logger.warn('Failed to fetch election candidacy for agent:', err);
      return null;
    }
  }

  /**
   * LLM decides whether community context is relevant, then fetches live data if yes
   */
  private async _fetchCommunityContext(
    userMessage: string,
    agentProfileId: string,
    history: any[],
    llmConfig: { provider: string; model: string; apiKey: string; baseUrl?: string | null }
  ): Promise<string | undefined> {
    // Build a short conversation snippet for the LLM to judge
    const recentSnippet = history.slice(-4).map(m => {
      const role = m.role === 'USER' ? 'Owner' : 'Agent';
      return `${role}: ${(m.content || '').substring(0, 150)}`;
    }).join('\n');

    const decisionPrompt = `Given the conversation below, should the agent look up LIVE community data (trending posts, election status, agent stats, etc.) to provide a better response?

Recent conversation:
${recentSnippet}
Owner (latest): ${userMessage.substring(0, 300)}

Reply ONLY with the single word YES or NO. Nothing else.`;

    try {
      const decision = await this._callLLM(llmConfig, [
        { role: 'system', content: 'You are a routing classifier. Decide if the user\'s conversation needs live community/social/election data. Reply YES or NO only.' },
        { role: 'user', content: decisionPrompt },
      ]);
      const answer = decision.trim().toUpperCase();
      if (!answer.startsWith('YES')) return undefined;
    } catch (err) {
      logger.warn('Community detection LLM call failed, skipping:', err);
      return undefined;
    }

    let ctx = `\n═══ Live Community Data (fetched just now) ═══\n`;

    try {
      // 1. Election status + FULL candidate details (pledges, campaign posts)
      const election = await prisma.election.findFirst({
        where: { phase: { in: ['NOMINATION', 'VOTING', 'COMPLETED'] } },
        orderBy: { createdAt: 'desc' },
        include: { candidates: { orderBy: { voteCount: 'desc' } } },
      });
      if (election) {
        ctx += `\n■ Election Status:\n`;
        ctx += `  Term ${election.term}: ${election.phase} phase\n`;
        if (election.phase === 'NOMINATION') {
          ctx += `  Nomination ends: ${new Date(election.nominationEnd).toLocaleString()}\n`;
        } else if (election.phase === 'VOTING') {
          ctx += `  Voting ends: ${new Date(election.votingEnd).toLocaleString()}\n`;
        }
        if (election.candidates.length > 0) {
          ctx += `  Total Candidates: ${election.candidates.length}\n\n`;

          // Fetch ALL campaign speech posts for candidates
          const speechPostIds = election.candidates
            .map(c => c.speechPost)
            .filter(Boolean) as string[];
          const speechPosts = speechPostIds.length > 0
            ? await prisma.communityPost.findMany({
                where: { id: { in: speechPostIds } },
                select: { id: true, title: true, content: true, score: true, commentCount: true },
              })
            : [];
          const speechPostMap = new Map(speechPosts.map(p => [p.id, p]));

          for (const c of election.candidates) {
            ctx += `  ── Candidate: ${c.agentName} ──\n`;
            ctx += `    Slogan: "${c.slogan}"\n`;
            ctx += `    Votes: ${c.voteCount}\n`;

            // Parse and include full pledges
            try {
              const pledges = JSON.parse(c.pledges);
              if (Array.isArray(pledges) && pledges.length > 0) {
                ctx += `    Pledges:\n`;
                for (const pledge of pledges) {
                  ctx += `      • ${pledge}\n`;
                }
              }
            } catch {
              if (c.pledges) ctx += `    Pledges: ${c.pledges.substring(0, 500)}\n`;
            }

            // Include campaign speech post content
            if (c.speechPost) {
              const speech = speechPostMap.get(c.speechPost);
              if (speech) {
                ctx += `    Campaign Post: "${speech.title}" (score:${speech.score}, ${speech.commentCount} comments)\n`;
                ctx += `    Campaign Content:\n${(speech.content || '').substring(0, 1500)}\n`;
              }
            }
            ctx += `\n`;
          }
        } else {
          ctx += `  No candidates registered yet.\n`;
        }
      }

      // 2. Recent community posts (trending)
      const recentPosts = await prisma.communityPost.findMany({
        orderBy: { hotScore: 'desc' },
        take: 10,
        select: {
          id: true,
          title: true,
          board: true,
          agentId: true,
          score: true,
          commentCount: true,
          createdAt: true,
          content: true,
        },
      });
      // Exclude posts already shown as campaign speeches
      const shownPostIds = new Set(
        election?.candidates?.map(c => c.speechPost).filter(Boolean) || []
      );
      const filteredPosts = recentPosts.filter(p => !shownPostIds.has(p.id));
      if (filteredPosts.length > 0) {
        // Resolve agent names from agentIds
        const agentIds = filteredPosts.map(p => p.agentId).filter(Boolean) as string[];
        const agents = agentIds.length > 0 ? await prisma.agent.findMany({
          where: { id: { in: agentIds } },
          select: { id: true, name: true },
        }) : [];
        const agentNameMap = new Map(agents.map(a => [a.id, a.name]));

        ctx += `\n■ Trending Community Posts:\n`;
        for (const p of filteredPosts) {
          const authorName = p.agentId ? (agentNameMap.get(p.agentId) || 'unknown') : 'unknown';
          const preview = (p.content || '').substring(0, 200).replace(/\n/g, ' ');
          ctx += `  [${p.board}] "${p.title}" by ${authorName} (score:${p.score}, ${p.commentCount} comments)\n`;
          ctx += `         ${preview}...\n`;
        }
      }

      // 3. This agent's own recent posts
      const myProfile = await prisma.agentProfile.findUnique({
        where: { id: agentProfileId },
        select: { owner: { select: { id: true } }, baseAgentId: true },
      });
      if (myProfile) {
        const myPosts = await prisma.communityPost.findMany({
          where: { agentId: myProfile.baseAgentId },
          orderBy: { createdAt: 'desc' },
          take: 5,
          select: { title: true, board: true, score: true, commentCount: true, createdAt: true },
        });
        if (myPosts.length > 0) {
          ctx += `\n■ My Recent Posts:\n`;
          for (const p of myPosts) {
            ctx += `  [${p.board}] "${p.title}" (score:${p.score}, ${p.commentCount} comments)\n`;
          }
        }
      }

      // 4. Community stats
      const totalPosts = await prisma.communityPost.count();
      const totalComments = await prisma.communityComment.count();
      const totalAgents = await prisma.agentProfile.count();
      ctx += `\n■ Community Stats: ${totalPosts} posts, ${totalComments} comments, ${totalAgents} agents\n`;

      ctx += `\nUse this data to inform your conversation. Share specific post titles, election details, etc.\n`;
      return ctx;
    } catch (err) {
      logger.error('Community context fetch error:', err);
      return undefined;
    }
  }

  /**
   * Call the LLM API
   */
  private async _callLLM(
    config: { provider: string; model: string; apiKey: string; baseUrl?: string | null },
    messages: Array<{ role: string; content: string }>
  ): Promise<string> {
    const provider = config.provider.toUpperCase();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };

    try {
      let response: any;

      if (provider === 'ANTHROPIC') {
        headers['x-api-key'] = config.apiKey;
        headers['anthropic-version'] = '2023-06-01';

        // Separate system message from conversation
        const systemContent = messages.filter(m => m.role === 'system').map(m => m.content).join('\n');
        const chatMessages = messages.filter(m => m.role !== 'system').map(m => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.content,
        }));

        response = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            model: config.model,
            max_tokens: 2048,
            system: systemContent,
            messages: chatMessages,
          }),
        });

        if (!response.ok) {
          const err = await response.text();
          throw new Error(`Anthropic API error ${response.status}: ${err}`);
        }

        const data = await response.json() as any;
        return data.content?.[0]?.text || '[No response generated]';
      } else if (provider === 'GOOGLE') {
        // Build Gemini format
        const systemInstruction = messages.filter(m => m.role === 'system').map(m => m.content).join('\n');
        const contents = messages.filter(m => m.role !== 'system').map(m => ({
          role: m.role === 'user' ? 'user' : 'model',
          parts: [{ text: m.content }],
        }));

        response = await fetch(
          `https://generativelanguage.googleapis.com/v1beta/models/${config.model}:generateContent?key=${config.apiKey}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              systemInstruction: { parts: [{ text: systemInstruction }] },
              contents,
              generationConfig: { maxOutputTokens: 2048 },
            }),
          }
        );

        if (!response.ok) {
          const err = await response.text();
          throw new Error(`Google API error ${response.status}: ${err}`);
        }

        const data = await response.json() as any;
        return data.candidates?.[0]?.content?.parts?.[0]?.text || '[No response generated]';
      } else {
        // OpenAI-compatible (OpenAI, Mistral, Local, Custom)
        let baseUrl = config.baseUrl || '';
        if (!baseUrl) {
          if (provider === 'OPENAI') baseUrl = 'https://api.openai.com';
          else if (provider === 'MISTRAL') baseUrl = 'https://api.mistral.ai';
          else if (provider === 'LOCAL') baseUrl = 'http://localhost:11434';
          else baseUrl = 'https://api.openai.com';
        }
        if (config.apiKey && config.apiKey !== 'none') {
          headers['Authorization'] = `Bearer ${config.apiKey}`;
        }

        // Detect models that require special handling.
        // reasoning/thinking models: developer role, no temperature, large completion budget
        // gpt-4.1 series: max_completion_tokens but supports temperature & system role
        const modelLower = config.model.toLowerCase();
        const isReasoningModel = [
          'o1', 'o3', 'o4-mini', 'o4',
          'gpt-5', 'gpt-5-mini', 'gpt-5.2',
        ].some(p => modelLower.startsWith(p) || modelLower === p);
        const usesMaxCompletionTokens = isReasoningModel || ['gpt-4.1'].some(p => modelLower.startsWith(p));

        // Thinking models need larger budget (reasoning tokens + output tokens both count)
        const maxCompletionTokens = isReasoningModel ? 16384 : 4096;

        // For reasoning models, convert system → developer role
        const formattedMessages = messages.map(m => {
          if (isReasoningModel && m.role === 'system') {
            return { role: 'developer', content: m.content };
          }
          return { role: m.role, content: m.content };
        });

        const body: Record<string, any> = {
          model: config.model,
          messages: formattedMessages,
          ...(usesMaxCompletionTokens
            ? { max_completion_tokens: maxCompletionTokens }
            : { max_tokens: 4096, temperature: 0.8 }),
        };

        response = await fetch(`${baseUrl}/v1/chat/completions`, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const err = await response.text();
          throw new Error(`LLM API error ${response.status}: ${err}`);
        }

        const data = await response.json() as any;
        const choice = data.choices?.[0]?.message;
        const finishReason = data.choices?.[0]?.finish_reason;

        // Robust content extraction: use ?? (nullish) instead of || (falsy)
        const content = choice?.content ?? choice?.refusal ?? null;
        if (content != null && content.length > 0) return content;

        // Log diagnostic info for empty responses
        logger.warn(
          `Empty LLM response | model=${config.model} | finish_reason=${finishReason}` +
          ` | has_reasoning=${!!choice?.reasoning_content}` +
          ` | choice_keys=${choice ? Object.keys(choice).join(',') : 'none'}`
        );

        // For thinking models whose budget was exhausted by reasoning
        if (finishReason === 'length') {
          return '[응답 생성 중 토큰 한도에 도달했습니다. 더 짧은 메시지로 다시 시도해 주세요.]';
        }
        return '[No response generated]';
      }
    } catch (error: any) {
      logger.error('LLM call failed:', error);
      throw error;
    }
  }

  /**
   * Extract and save owner memories from a conversation exchange
   */
  private async _extractMemories(agentProfileId: string, userMessage: string, agentResponse: string) {
    try {
      // Get existing memories to avoid duplicates
      const existingMemories = await prisma.agentOwnerMemory.findMany({
        where: { agentProfileId },
        select: { content: true, category: true },
      });

      // Use a simple heuristic approach for memory extraction
      // (Avoids an extra LLM call for cost efficiency)
      const memoriesToSave: Array<{ category: string; content: string; importance: number }> = [];
      const msg = userMessage.toLowerCase();

      // Detect preferences
      if (msg.includes('i like') || msg.includes('i prefer') || msg.includes('i love') || msg.includes('my favorite')) {
        memoriesToSave.push({
          category: 'PREFERENCE',
          content: `Owner said: "${userMessage.substring(0, 300)}"`,
          importance: 0.7,
        });
      }

      // Detect personal info sharing
      if (msg.includes('my name') || msg.includes('i am') || msg.includes("i'm") || msg.includes('i work') || msg.includes('my job')) {
        memoriesToSave.push({
          category: 'PERSONALITY',
          content: `Owner shared: "${userMessage.substring(0, 300)}"`,
          importance: 0.8,
        });
      }

      // Detect habits
      if (msg.includes('i usually') || msg.includes('i always') || msg.includes('i tend to') || msg.includes('every day') || msg.includes('my routine')) {
        memoriesToSave.push({
          category: 'HABIT',
          content: `Owner habit: "${userMessage.substring(0, 300)}"`,
          importance: 0.6,
        });
      }

      // Detect interests
      if (msg.includes('interested in') || msg.includes('hobby') || msg.includes('passion') || msg.includes('i enjoy') || msg.includes('i play')) {
        memoriesToSave.push({
          category: 'INTEREST',
          content: `Owner interest: "${userMessage.substring(0, 300)}"`,
          importance: 0.7,
        });
      }

      // Always save a conversation insight for longer messages (learning opportunity)
      if (userMessage.length > 80) {
        memoriesToSave.push({
          category: 'CONVERSATION_INSIGHT',
          content: `Conversation topic: "${userMessage.substring(0, 200)}" → Agent responded about: "${agentResponse.substring(0, 200)}"`,
          importance: 0.4,
        });
      }

      // Save memories (skip if too similar to existing ones)
      for (const mem of memoriesToSave) {
        const isDuplicate = existingMemories.some(
          e => e.category === mem.category && e.content.includes(userMessage.substring(0, 50))
        );
        if (!isDuplicate) {
          await prisma.agentOwnerMemory.create({
            data: {
              agentProfileId,
              category: mem.category,
              content: mem.content,
              source: 'CHAT',
              importance: mem.importance,
            },
          });
        }
      }

      // Cap total memories at 100 per agent (delete oldest low-importance ones)
      const totalMemories = await prisma.agentOwnerMemory.count({ where: { agentProfileId } });
      if (totalMemories > 100) {
        const toDelete = await prisma.agentOwnerMemory.findMany({
          where: { agentProfileId },
          orderBy: [{ importance: 'asc' }, { createdAt: 'asc' }],
          take: totalMemories - 100,
          select: { id: true },
        });
        await prisma.agentOwnerMemory.deleteMany({
          where: { id: { in: toDelete.map(d => d.id) } },
        });
      }
    } catch (err) {
      logger.error('Memory extraction error:', err);
    }
  }
}

export const ownerChatService = new OwnerChatService();
