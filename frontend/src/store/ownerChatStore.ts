import { create } from 'zustand';
import { api } from '../lib/api';
import { wsClient } from '../lib/websocket';

// ════════════════════════════════════════════════════════════════
// Types
// ════════════════════════════════════════════════════════════════

export interface OwnerChatRoom {
  id: string;
  userId: string;
  type: 'INDIVIDUAL' | 'GROUP';
  name: string | null;
  agentProfileId: string | null;
  agentProfile: {
    id: string;
    displayName: string;
    avatar: string | null;
    baseAgent: { name: string; icon: string | null };
  } | null;
  participants: Array<{
    id: string;
    agentProfileId: string;
    agentProfile: {
      id: string;
      displayName: string;
      avatar: string | null;
      baseAgent: { icon: string | null };
    };
  }>;
  lastMessageAt: string | null;
  lastMessagePreview: string | null;
  createdAt: string;
}

export interface OwnerChatMessage {
  id: string;
  chatId: string;
  role: 'USER' | 'AGENT';
  userId: string | null;
  agentProfileId: string | null;
  agentProfile: { displayName: string; avatar: string | null } | null;
  content: string;
  isProactive: boolean;
  proactiveReason: string | null;
  createdAt: string;
}

export interface AgentOwnerMemory {
  id: string;
  agentProfileId: string;
  category: string;
  content: string;
  source: string;
  importance: number;
  createdAt: string;
}

// ════════════════════════════════════════════════════════════════
// Store
// ════════════════════════════════════════════════════════════════

interface OwnerChatState {
  rooms: OwnerChatRoom[];
  activeRoom: OwnerChatRoom | null;
  messages: OwnerChatMessage[];
  memories: AgentOwnerMemory[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;

  loadRooms: () => Promise<void>;
  openIndividualChat: (agentProfileId: string) => Promise<void>;
  createGroupChat: (name: string, agentProfileIds: string[]) => Promise<void>;
  selectRoom: (roomId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  deleteRoom: (roomId: string) => Promise<void>;
  addParticipants: (roomId: string, agentProfileIds: string[]) => Promise<void>;
  loadMemories: (agentProfileId: string) => Promise<void>;
  subscribeGroupDiscussion: () => () => void;
  clearError: () => void;
}

export const useOwnerChatStore = create<OwnerChatState>((set, get) => ({
  rooms: [],
  activeRoom: null,
  messages: [],
  memories: [],
  isLoading: false,
  isSending: false,
  error: null,

  loadRooms: async () => {
    try {
      set({ isLoading: true, error: null });
      const resp = await api.ownerChat.listRooms();
      const rooms = resp?.data ?? resp;
      set({ rooms: Array.isArray(rooms) ? rooms : [], isLoading: false });
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  openIndividualChat: async (agentProfileId: string) => {
    try {
      set({ isLoading: true, error: null });
      const resp = await api.ownerChat.getOrCreateIndividual(agentProfileId);
      const room = resp?.data ?? resp;
      set({
        activeRoom: room,
        messages: room?.messages || [],
        isLoading: false,
      });
      // Refresh rooms list
      get().loadRooms();
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  createGroupChat: async (name: string, agentProfileIds: string[]) => {
    try {
      set({ isLoading: true, error: null });
      const resp = await api.ownerChat.createGroup(name, agentProfileIds);
      const room = resp?.data ?? resp;
      set({
        activeRoom: room,
        messages: [],
        isLoading: false,
      });
      get().loadRooms();
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  selectRoom: async (roomId: string) => {
    try {
      set({ isLoading: true, error: null });
      const resp = await api.ownerChat.getMessages(roomId);
      const room = get().rooms.find(r => r.id === roomId) || null;
      const msgs = resp?.data ?? resp;
      set({
        activeRoom: room,
        messages: Array.isArray(msgs) ? msgs : [],
        isLoading: false,
      });
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  sendMessage: async (content: string) => {
    const { activeRoom } = get();
    if (!activeRoom) return;

    try {
      set({ isSending: true, error: null });

      // Optimistically add user message
      const tempUserMsg: OwnerChatMessage = {
        id: `temp-${Date.now()}`,
        chatId: activeRoom.id,
        role: 'USER',
        userId: null,
        agentProfileId: null,
        agentProfile: null,
        content,
        isProactive: false,
        proactiveReason: null,
        createdAt: new Date().toISOString(),
      };
      set(s => ({ messages: [...s.messages, tempUserMsg] }));

      // Send to backend (gets AI response)
      const resp = await api.ownerChat.sendMessage(activeRoom.id, content);
      const respData = resp?.data ?? resp;
      const { userMessage, agentMessages } = respData;

      // Replace temp message with real one and add agent responses
      set(s => ({
        messages: [
          ...s.messages.filter(m => m.id !== tempUserMsg.id),
          userMessage,
          ...agentMessages,
        ],
        isSending: false,
      }));

      // Update rooms list
      get().loadRooms();
    } catch (err: any) {
      set({ error: err.message, isSending: false });
    }
  },

  deleteRoom: async (roomId: string) => {
    try {
      await api.ownerChat.deleteRoom(roomId);
      set(s => ({
        rooms: s.rooms.filter(r => r.id !== roomId),
        activeRoom: s.activeRoom?.id === roomId ? null : s.activeRoom,
        messages: s.activeRoom?.id === roomId ? [] : s.messages,
      }));
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  addParticipants: async (roomId: string, agentProfileIds: string[]) => {
    try {
      await api.ownerChat.addParticipants(roomId, agentProfileIds);
      get().loadRooms();
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  loadMemories: async (agentProfileId: string) => {
    try {
      const resp = await api.ownerChat.getMemories(agentProfileId);
      const mems = resp?.data ?? resp;
      set({ memories: Array.isArray(mems) ? mems : [] });
    } catch (err: any) {
      set({ error: err.message });
    }
  },

  subscribeGroupDiscussion: () => {
    const cleanup = wsClient.on('owner_chat:new_message', (data: { chatId: string; message: OwnerChatMessage }) => {
      if (!data?.chatId || !data?.message) return;
      const { activeRoom, messages: currentMessages } = get();
      // Only append if this message belongs to the currently viewed chat
      if (activeRoom && activeRoom.id === data.chatId) {
        // Avoid duplicates
        const exists = currentMessages.some(m => m.id === data.message.id);
        if (!exists) {
          set(s => ({ messages: [...s.messages, data.message] }));
        }
      }
      // Also refresh rooms list to update lastMessagePreview
      get().loadRooms();
    });
    return cleanup;
  },

  clearError: () => set({ error: null }),
}));
