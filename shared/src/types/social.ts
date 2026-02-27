// ============================================
// Agent Social System Types
// ============================================

// ─── Agent Profile ──────────────────────────────────────────

export interface AgentProfile {
  id: string;
  purchaseId: string;
  ownerId: string;
  baseAgentId: string;
  displayName: string;
  bio: string;
  avatar?: string;
  selfPrompt?: string;
  selfPromptHash?: string;
  followerCount: number;
  followingCount: number;
  friendCount: number;
  postCount: number;
  totalCreditsEarned: number;
  reputation: number;
  isActive: boolean;
  lastActiveAt: string;
  createdAt: string;
  updatedAt: string;
  // Joined relations
  baseAgent?: AgentProfileBaseAgent;
  owner?: AgentProfileOwner;
}

export interface AgentProfileBaseAgent {
  id?: string;
  name: string;
  slug: string;
  tier: string;
  domain: string;
  icon: string;
  category?: string;
}

export interface AgentProfileOwner {
  id?: string;
  username: string;
  displayName: string;
  avatar?: string;
}

export interface AgentProfileSummary {
  id: string;
  displayName: string;
  bio: string;
  avatar?: string;
  followerCount: number;
  followingCount: number;
  friendCount: number;
  reputation: number;
  baseAgent: AgentProfileBaseAgent;
  owner?: { username: string; displayName: string };
}

// ─── Follow / Friend ────────────────────────────────────────

export type FollowStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED';

export interface AgentFollow {
  id: string;
  followerId: string;
  targetId: string;
  status: FollowStatus;
  isMutual: boolean;
  createdAt: string;
  updatedAt: string;
  follower?: AgentProfileSummary;
  target?: AgentProfileSummary;
}

export interface AgentRelationship {
  aFollowsB: boolean;
  bFollowsA: boolean;
  isFriend: boolean;
  pendingFromA: boolean;
  pendingFromB: boolean;
}

export interface FollowerList {
  followers: (AgentProfileSummary & { followedAt: string; isMutual: boolean })[];
  total: number;
  page: number;
  limit: number;
}

export interface FollowingList {
  following: (AgentProfileSummary & { followedAt: string; isMutual: boolean })[];
  total: number;
  page: number;
  limit: number;
}

// ─── Chat System ────────────────────────────────────────────

export type ChatType = 'DM' | 'GROUP';
export type ChatMemberRole = 'MEMBER' | 'ADMIN';
export type MessageType = 'TEXT' | 'SYSTEM';

export interface AgentChatRoom {
  id: string;
  name?: string;
  type: ChatType;
  createdById?: string;
  lastMessageAt?: string;
  lastMessagePreview?: string;
  createdAt: string;
  updatedAt: string;
  members: AgentChatMember[];
  // UI-computed
  myRole?: ChatMemberRole;
  lastReadAt?: string;
  unreadCount?: number;
  myAgentProfile?: { id: string; displayName: string };
}

export interface AgentChatMember {
  id: string;
  chatRoomId: string;
  profileId: string;
  role: ChatMemberRole;
  lastReadAt?: string;
  joinedAt: string;
  profile: {
    id: string;
    displayName: string;
    avatar?: string;
    baseAgent?: { icon: string };
    ownerId?: string;
  };
}

export interface AgentMessage {
  id: string;
  chatRoomId: string;
  senderId: string;
  content: string;
  messageType: MessageType;
  createdAt: string;
  sender: {
    id: string;
    displayName: string;
    avatar?: string;
  };
}

export interface ChatMessageList {
  messages: AgentMessage[];
  total: number;
  page: number;
  limit: number;
}

// ─── Agent Notifications ────────────────────────────────────

export type AgentNotificationType =
  | 'FOLLOW_REQUEST'
  | 'FOLLOW_ACCEPTED'
  | 'NEW_FOLLOWER'
  | 'NEW_MESSAGE'
  | 'GROUP_INVITE'
  | 'FOLLOWER_POST'
  | 'TIP_RECEIVED'
  | 'MENTION';

export interface AgentNotification {
  id: string;
  profileId: string;
  type: AgentNotificationType;
  title: string;
  message: string;
  data?: string;
  read: boolean;
  createdAt: string;
}

export interface AgentNotificationList {
  notifications: AgentNotification[];
  unreadCount: number;
}
