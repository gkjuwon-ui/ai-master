/**
 * Social Store — State management for Agent Social System
 * 
 * Manages:
 * - Agent profiles owned by the user
 * - Profile details with followers, following, friends
 * - Chat rooms and messages (spectating)
 * - Notifications
 */

import { create } from 'zustand';
import { api } from '../lib/api';

// ─── Types ──────────────────────────────────────────────────

interface AgentProfileBaseAgent {
  id?: string;
  name: string;
  slug: string;
  tier: string;
  domain: string;
  icon: string;
}

interface AgentProfileOwner {
  id?: string;
  username: string;
  displayName: string;
}

interface AgentProfile {
  id: string;
  purchaseId: string;
  ownerId: string;
  baseAgentId: string;
  displayName: string;
  bio: string;
  avatar?: string;
  selfPrompt?: string;
  followerCount: number;
  followingCount: number;
  friendCount: number;
  postCount: number;
  totalCreditsEarned: number;
  reputation: number;
  isActive: boolean;
  lastActiveAt: string;
  createdAt: string;
  baseAgent?: AgentProfileBaseAgent;
  owner?: AgentProfileOwner;
}

interface AgentFollowEntry {
  id: string;
  displayName: string;
  bio?: string;
  avatar?: string;
  followerCount: number;
  reputation: number;
  baseAgent?: AgentProfileBaseAgent;
  followedAt?: string;
  isMutual?: boolean;
}

interface ChatMember {
  id: string;
  profileId: string;
  role: string;
  profile: {
    id: string;
    displayName: string;
    avatar?: string;
  };
}

interface ChatRoom {
  id: string;
  name?: string;
  type: 'DM' | 'GROUP';
  lastMessageAt?: string;
  lastMessagePreview?: string;
  members: ChatMember[];
  myRole?: string;
  myAgentProfile?: { id: string; displayName: string };
  myAgentProfiles?: { id: string; displayName: string }[];
}

interface ChatMessage {
  id: string;
  chatRoomId: string;
  senderId: string;
  content: string;
  messageType: 'TEXT' | 'SYSTEM';
  tipAmount?: number | null;
  tipTransferId?: string | null;
  createdAt: string;
  sender: {
    id: string;
    displayName: string;
    avatar?: string;
  };
}

interface AgentNotification {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  createdAt: string;
}

// ─── Store ──────────────────────────────────────────────────

interface SocialState {
  // My agent profiles
  myProfiles: AgentProfile[];
  selectedProfile: AgentProfile | null;
  
  // Viewing another profile
  viewingProfile: AgentProfile | null;
  
  // Follow data
  followers: AgentFollowEntry[];
  following: AgentFollowEntry[];
  friends: AgentFollowEntry[];
  
  // Chat
  chatRooms: ChatRoom[];
  activeChatRoom: ChatRoom | null;
  messages: ChatMessage[];
  
  // Notifications
  notifications: AgentNotification[];
  unreadCount: number;
  
  // UI state
  isLoading: boolean;
  error: string | null;
  activeTab: 'profiles' | 'chat' | 'activity';

  // Actions
  fetchMyProfiles: () => Promise<void>;
  selectProfile: (profileId: string) => Promise<void>;
  viewProfile: (profileId: string) => Promise<void>;
  fetchFollowers: (profileId: string) => Promise<void>;
  fetchFollowing: (profileId: string) => Promise<void>;
  fetchFriends: (profileId: string) => Promise<void>;
  fetchChatRooms: () => Promise<void>;
  fetchMessages: (roomId: string) => Promise<void>;
  fetchNotifications: (profileId: string) => Promise<void>;
  markNotificationsRead: (profileId: string) => Promise<void>;
  setActiveTab: (tab: 'profiles' | 'chat' | 'activity') => void;
  setActiveChatRoom: (room: ChatRoom | null) => void;
}

export const useSocialStore = create<SocialState>((set, get) => ({
  myProfiles: [],
  selectedProfile: null,
  viewingProfile: null,
  followers: [],
  following: [],
  friends: [],
  chatRooms: [],
  activeChatRoom: null,
  messages: [],
  notifications: [],
  unreadCount: 0,
  isLoading: false,
  error: null,
  activeTab: 'profiles',

  fetchMyProfiles: async () => {
    set({ isLoading: true, error: null });
    try {
      const resp = await api.get<{ success: boolean; data: AgentProfile[] }>('/api/social/my-profiles');
      const profiles = resp?.data ?? resp;
      set({ myProfiles: Array.isArray(profiles) ? profiles : [], isLoading: false });
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  selectProfile: async (profileId: string) => {
    const profile = get().myProfiles.find(p => p.id === profileId);
    if (profile) {
      set({ selectedProfile: profile });
      // Load social data + refresh profile counters in parallel
      const [, , , , freshProfile] = await Promise.all([
        get().fetchFollowers(profileId),
        get().fetchFollowing(profileId),
        get().fetchFriends(profileId),
        get().fetchNotifications(profileId),
        api.get<{ success: boolean; data: AgentProfile }>(`/api/social/profiles/${profileId}`).catch(() => null),
      ]);
      // Update selectedProfile with recalculated counters from backend
      const fp = freshProfile?.data ?? freshProfile;
      if (fp) {
        set({ selectedProfile: { ...profile, ...fp } });
      }
    }
  },

  viewProfile: async (profileId: string) => {
    set({ isLoading: true });
    try {
      const resp = await api.get<{ success: boolean; data: AgentProfile }>(`/api/social/profiles/${profileId}`);
      set({ viewingProfile: resp?.data ?? resp ?? null, isLoading: false });
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  },

  fetchFollowers: async (profileId: string) => {
    try {
      const resp = await api.get<{ success: boolean; data: { followers: AgentFollowEntry[] } }>(
        `/api/social/profiles/${profileId}/followers`
      );
      const fData = resp?.data ?? resp;
      set({ followers: fData?.followers ?? (Array.isArray(fData) ? fData : []) });
    } catch (err: any) {
      console.error('Failed to fetch followers:', err);
    }
  },

  fetchFollowing: async (profileId: string) => {
    try {
      const resp = await api.get<{ success: boolean; data: { following: AgentFollowEntry[] } }>(
        `/api/social/profiles/${profileId}/following`
      );
      const fgData = resp?.data ?? resp;
      set({ following: fgData?.following ?? (Array.isArray(fgData) ? fgData : []) });
    } catch (err: any) {
      console.error('Failed to fetch following:', err);
    }
  },

  fetchFriends: async (profileId: string) => {
    try {
      const resp = await api.get<{ success: boolean; data: AgentFollowEntry[] }>(
        `/api/social/profiles/${profileId}/friends`
      );
      const frData = resp?.data ?? resp;
      set({ friends: Array.isArray(frData) ? frData : [] });
    } catch (err: any) {
      console.error('Failed to fetch friends:', err);
    }
  },

  fetchChatRooms: async () => {
    try {
      const resp = await api.get<{ success: boolean; data: ChatRoom[] }>('/api/social/chat/owner-rooms');
      const crData = resp?.data ?? resp;
      set({ chatRooms: Array.isArray(crData) ? crData : [] });
    } catch (err: any) {
      console.error('Failed to fetch chat rooms:', err);
    }
  },

  fetchMessages: async (roomId: string) => {
    try {
      const resp = await api.get<{ success: boolean; data: { messages: ChatMessage[] } }>(
        `/api/social/chat/${roomId}/messages`
      );
      const mData = resp?.data ?? resp;
      set({ messages: mData?.messages ?? (Array.isArray(mData) ? mData : []) });
    } catch (err: any) {
      console.error('Failed to fetch messages:', err);
    }
  },

  fetchNotifications: async (profileId: string) => {
    try {
      const resp = await api.get<{ success: boolean; data: { notifications: AgentNotification[]; unreadCount: number } }>(
        `/api/social/notifications/${profileId}`
      );
      set({
        notifications: (resp?.data ?? resp)?.notifications || [],
        unreadCount: (resp?.data ?? resp)?.unreadCount || 0,
      });
    } catch (err: any) {
      console.error('Failed to fetch notifications:', err);
    }
  },

  markNotificationsRead: async (profileId: string) => {
    try {
      await api.post(`/api/social/notifications/${profileId}/read`, {});
      set({ unreadCount: 0, notifications: get().notifications.map(n => ({ ...n, read: true })) });
    } catch (err: any) {
      console.error('Failed to mark notifications read:', err);
    }
  },

  setActiveTab: (tab) => set({ activeTab: tab }),
  
  setActiveChatRoom: (room) => {
    set({ activeChatRoom: room });
    if (room) {
      get().fetchMessages(room.id);
    }
  },
}));
