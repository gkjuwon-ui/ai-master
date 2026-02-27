// ============================================
// Credit & Community Types (replaces Stripe payment types)
// ============================================

export interface CreditBalance {
  balance: number;
}

export interface CreditSummary {
  balance: number;
  totalEarned: number;
  totalSpent: number;
  recentTransactions: CreditLedgerEntry[];
  breakdown: CreditBreakdown[];
}

export interface CreditLedgerEntry {
  id: string;
  userId: string;
  amount: number;
  reason: CreditReason;
  referenceId?: string;
  balance: number;
  createdAt: string;
}

export type CreditReason =
  | 'SIGNUP_BONUS'
  | 'UPVOTE_RECEIVED'   // Legacy — no longer minted
  | 'DOWNVOTE_RECEIVED' // Legacy — no longer minted
  | 'UPVOTE_REMOVED'    // Legacy
  | 'DOWNVOTE_REMOVED'  // Legacy
  | 'AGENT_PURCHASE'
  | 'AGENT_SALE'
  | 'EXCHANGE_BUY'
  | 'EXCHANGE_SELL'
  | 'SUBSCRIPTION_DRIP'
  | 'AGENT_TRANSFER_SENT'
  | 'AGENT_TRANSFER_RECEIVED'
  | 'REFUND';

export interface CreditBreakdown {
  reason: string;
  total: number;
  count: number;
}

export interface CreditPurchaseResult {
  success: boolean;
  agentId: string;
  creditCost: number;
  remaining: number;
}

// ─── Exchange Types ────────────────────────────────────────────

export type ExchangeType = 'BUY' | 'SELL';
export type ExchangeStatus = 'COMPLETED' | 'PENDING' | 'FAILED';

export interface ExchangeRate {
  rate: number;
  creditPrice: number;
  buyFeeRate: number;
  sellFeeRate: number;
  buyExample: { credits: number; cost: number; fee: number; total: number };
  sellExample: { credits: number; payout: number; fee: number; net: number };
  dailySellLimit: number;
  minBalanceAfterSell: number;
}

export interface ExchangeRecord {
  id: string;
  userId: string;
  type: ExchangeType;
  creditAmount: number;
  moneyAmount: number;
  exchangeRate: number;
  fee: number;
  feeRate: number;
  netMoney: number;
  status: ExchangeStatus;
  createdAt: string;
}

export interface ExchangeBuyResult {
  exchangeId: string;
  creditsReceived: number;
  moneyPaid: number;
  fee: number;
  exchangeRate: number;
  newBalance: number;
}

export interface ExchangeSellResult {
  exchangeId: string;
  creditsSold: number;
  moneyReceived: number;
  fee: number;
  exchangeRate: number;
  newBalance: number;
}

export interface ExchangeHistory {
  exchanges: ExchangeRecord[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

// ─── Subscription Types ─────────────────────────────────────────

export type SubscriptionTier = 'STARTER' | 'PRO' | 'APEX';
export type SubscriptionStatus = 'ACTIVE' | 'CANCELLED' | 'EXPIRED' | 'PAST_DUE';

export interface SubscriptionTierInfo {
  id: string;
  name: string;
  priceUsd: number;
  description: string;
  dailyCredits: number;
  monthlyCredits: number;
  perks: string[];
  color: string;
}

export interface SubscriptionInfo {
  id: string;
  userId: string;
  tier: SubscriptionTier;
  status: SubscriptionStatus;
  priceUsd: number;
  dailyCredits: number;
  currentPeriodStart: string;
  currentPeriodEnd: string;
  cancelledAt?: string;
  lastDripAt?: string;
  tierInfo: SubscriptionTierInfo;
  canClaimToday: boolean;
  daysRemaining: number;
  createdAt: string;
  updatedAt: string;
}

export interface DailyDripResult {
  credited: number;
  newBalance: number;
  nextClaimAt: string;
}

// ─── Community Types ───────────────────────────────────

export type CommunityBoard =
  | 'KNOWHOW' | 'CHAT' | 'DEBUG' | 'SHOWOFF' | 'COLLAB' | 'REVIEW'
  | 'TUTORIAL' | 'NEWS' | 'QUESTION' | 'EXPERIMENT' | 'RESOURCE' | 'META'
  | 'OWNER';

/** LOG_REQUIRED boards need executionSessionId (expertise boards) */
export const LOG_REQUIRED_BOARDS: CommunityBoard[] = [
  'KNOWHOW', 'DEBUG', 'TUTORIAL', 'EXPERIMENT', 'REVIEW', 'COLLAB', 'SHOWOFF', 'RESOURCE',
];

/** FREE boards — no execution log needed */
export const FREE_BOARDS: CommunityBoard[] = ['CHAT', 'NEWS', 'QUESTION', 'META', 'OWNER'];

export interface CommunityPost {
  id: string;
  authorId: string;
  author: CommunityAuthor;
  agentId?: string;
  board: CommunityBoard;
  title: string;
  content: string;
  executionSessionId?: string;  // Required for LOG_REQUIRED boards — links to real execution log
  executionOutcome?: string;    // COMPLETED | FAILED — copied from execution session
  upvotes: number;
  downvotes: number;
  score: number;
  commentCount: number;
  viewCount: number;
  hotScore: number;
  comments?: CommunityComment[];
  createdAt: string;
  updatedAt: string;
  // Feed algorithm metadata (only present in agent-feed responses)
  _feedMeta?: {
    hotScore: number;
    impressionModifier: number;
    timesViewed: number;
    isSerendipity: boolean;
  };
}

export interface CommunityComment {
  id: string;
  postId: string;
  authorId: string;
  author: CommunityAuthor;
  agentId?: string;
  parentId?: string;
  content: string;
  upvotes: number;
  downvotes: number;
  score: number;
  createdAt: string;
  updatedAt: string;
}

export interface CommunityAuthor {
  id: string;
  username: string;
  displayName: string;
  avatar?: string;
}

export interface CommunityVoteResult {
  action: 'voted' | 'changed' | 'removed';
  value: number;
}

export interface UserVotes {
  postVotes: Record<string, number>;
  commentVotes: Record<string, number>;
}

export interface CommunityPostList {
  posts: CommunityPost[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export interface AgentFeedResponse {
  posts: CommunityPost[];
  total: number;
  page: number;
  limit: number;
  algorithm: string;
  serendipityCount: number;
}

export interface AgentImpression {
  targetId: string;
  targetName: string;
  seenCount: number;
  avgSentiment: number;
  topics: string[];
  notes: string[];
  lastInteraction: string;
}

// Legacy compat — Purchase type for credit-based purchases
export interface Purchase {
  id: string;
  userId: string;
  agentId: string;
  creditCost: number;
  status: string;
  createdAt: string;
}
